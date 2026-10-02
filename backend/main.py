import importlib
import importlib.util
import json
import os
import re
import secrets
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from backend.catalog import MODELS, MODEL_MAP

ROOT = Path(__file__).resolve().parent
DATA = Path(os.getenv("MEDICAL_DATA_DIR", str(ROOT / "data")))
CONFIG = Path(os.getenv("MODEL_CONFIG", str(ROOT / "models.local.json")))
TOKEN = os.getenv("MEDICAL_API_TOKEN", "")
MAX_UPLOAD = 100 * 1024 * 1024
pool = ThreadPoolExecutor(max_workers=1)
slots = threading.BoundedSemaphore(8)
security = HTTPBearer(auto_error=False)

def db():
    con = sqlite3.connect(DATA / "jobs.sqlite")
    con.row_factory = sqlite3.Row
    return con

@asynccontextmanager
async def lifespan(app):
    if not TOKEN:
        raise RuntimeError("Set MEDICAL_API_TOKEN before starting the server.")
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "uploads").mkdir(exist_ok=True)
    (DATA / "results").mkdir(exist_ok=True)
    with db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, name TEXT, path TEXT, size INTEGER)")
        con.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, model_id TEXT, task TEXT, status TEXT, created_at TEXT, error TEXT, result_path TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS threads (id TEXT PRIMARY KEY, title TEXT, messages TEXT, updated_at TEXT)")
        if "report_ids" not in [row[1] for row in con.execute("PRAGMA table_info(threads)")]:
            con.execute("ALTER TABLE threads ADD COLUMN report_ids TEXT NOT NULL DEFAULT '[]'")
        con.execute("UPDATE jobs SET status='failed', error='Server restarted before completion.' WHERE status IN ('queued','running')")
    yield
    pool.shutdown(wait=True)

app = FastAPI(title="Viniścaya Medical Model API", version="1.0.0", lifespan=lifespan)

def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if not credentials or not secrets.compare_digest(credentials.credentials, TOKEN):
        raise HTTPException(401, "Invalid API token.")

def configurations():
    if not CONFIG.exists():
        return {}
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        raise HTTPException(503, "Model configuration could not be read.")

def availability(model, config):
    if not config.get("enabled"):
        return "disabled", "Weights and adapter are not configured."
    if not config.get("weights") or not Path(config["weights"]).exists():
        return "missing_weights", "Local weights path does not exist."
    entry = config.get("adapter", model.get("builtin_adapter"))
    if not entry or ":" not in entry:
        return "missing_adapter", "A model-specific inference adapter is required."
    try:
        module, function = entry.split(":", 1)
        if importlib.util.find_spec(module) is None:
            return "missing_adapter", "Adapter module is not installed."
        if entry == "backend.adapters.hf:infer" and any(importlib.util.find_spec(p) is None for p in ["torch", "transformers"]):
            return "missing_dependencies", "Install the optional torch and transformers dependencies."
        if entry == "backend.adapters.esmfold:infer":
            import psutil
            if config.get("device", "cpu") == "cpu" and psutil.virtual_memory().available < 18 * 1024 ** 3:
                return "insufficient_memory", "Sequence folding needs at least 18 GB of available RAM with this CPU checkpoint. You can still view uploaded structures."
    except (ImportError, ModuleNotFoundError, ValueError):
        return "missing_adapter", "Adapter module is not installed."
    return "configured", "Configured locally; loading and inference are verified when a job runs."

@app.get("/health")
def health():
    return {"status": "ok", "service": "medical-models"}

@app.get("/v1/models", dependencies=[Depends(authorize)])
def models(category: str | None = None):
    config = configurations()
    result = []
    for model in MODELS:
        if category and category.lower() != model["category"].lower():
            continue
        status, reason = availability(model, config.get(model["id"], {}))
        result.append({k: v for k, v in model.items() if k != "builtin_adapter"} | {"status": status, "reason": reason})
    return {"models": result}

@app.post("/v1/files", status_code=201, dependencies=[Depends(authorize)])
async def upload(file: UploadFile = File(...)):
    suffix = "".join(Path(file.filename or "file").suffixes).lower()
    if suffix not in {".pdf", ".txt", ".docx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".svs", ".ndpi", ".dcm", ".nii", ".nii.gz", ".npy", ".npz", ".csv", ".edf", ".fif", ".pdb", ".cif", ".fasta", ".fa", ".a3m", ".mp4", ".avi"}:
        raise HTTPException(415, "Unsupported file format.")
    id = uuid4().hex
    path = DATA / "uploads" / (id + suffix)
    size = 0
    try:
        with path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "Upload limit is 100 MB.")
                output.write(chunk)
        if not size:
            raise HTTPException(400, "File is empty.")
        with db() as con:
            con.execute("INSERT INTO files VALUES (?,?,?,?)", (id, Path(file.filename or "file").name, str(path), size))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"id": id, "name": Path(file.filename or "file").name, "size": size}

class InferenceRequest(BaseModel):
    model_id: str = Field(max_length=80)
    task: str = Field(max_length=80)
    text: str | None = Field(default=None, max_length=16000)
    sequence: str | None = Field(default=None, max_length=4096)
    file_ids: list[str] = Field(default_factory=list, max_length=8)
    options: dict = Field(default_factory=dict)

def validate_input(request, model):
    modality = model["modality"]
    if modality == "text" and not (request.text or "").strip():
        raise HTTPException(422, "Text input is required.")
    if modality == "sequence":
        sequence = re.sub(r"\s+", "", request.sequence or "").upper()
        if not sequence or not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYBXZOU]+", sequence):
            raise HTTPException(422, "Provide a valid amino-acid sequence without FASTA headers.")
        request.sequence = sequence
    if modality not in {"text", "sequence"} and not request.file_ids:
        raise HTTPException(422, "At least one input file is required.")
    if model["id"] in {"phikon", "biomedclip-radiology", "biomedclip-neurology", "medsiglip-radiology", "medsiglip-neurology", "xrv-chest", "echonext"} and len(request.file_ids) != 1:
        raise HTTPException(422, "This analysis accepts exactly one input file.")
    if modality == "signal_video" and len(request.file_ids) < 2:
        raise HTTPException(422, "Provide both ECG and echo input files.")
    if model["id"] == "brats-mri" and len(request.file_ids) != 4:
        raise HTTPException(422, "BraTS needs four aligned T1ce, T1, T2 and FLAIR NIfTI volumes in that order.")
    files = []
    with db() as con:
        for id in request.file_ids:
            row = con.execute("SELECT path FROM files WHERE id=?", (id,)).fetchone()
            if not row:
                raise HTTPException(404, "Input file not found.")
            files.append(Path(row["path"]))
    return files

def run(id, request, files, config, entry):
    try:
        with db() as con:
            con.execute("UPDATE jobs SET status='running' WHERE id=?", (id,))
        if request.model_id == "brats-mri": request.options = {"artifact_dir": str(DATA / "results" / f"{id}-assets")}
        module, function = entry.split(":", 1)
        result = getattr(importlib.import_module(module), function)(request, files, config)
        with db() as con:
            names = [con.execute("SELECT name FROM files WHERE path=?", (str(file),)).fetchone()[0] for file in files]
        path = DATA / "results" / (id + ".json")
        path.write_text(json.dumps({"model_id": request.model_id, "task": request.task, "input": {"files": names, "file_ids": request.file_ids, "text": request.text, "sequence_length": len(request.sequence or ""), "synthetic_label": any("synthetic" in name.lower() for name in names)}, "output": result}, allow_nan=False), encoding="utf-8")
        with db() as con:
            con.execute("UPDATE jobs SET status='completed', result_path=? WHERE id=?", (str(path), id))
    except Exception as error:
        with db() as con:
            message = str(error)[:250] if isinstance(error, ValueError) else "Local inference failed. Check weights, dependencies, and input format."
            con.execute("UPDATE jobs SET status='failed', error=? WHERE id=?", (message, id))
    finally:
        slots.release()

@app.post("/v1/inference", status_code=202, dependencies=[Depends(authorize)])
def infer(request: InferenceRequest):
    model = MODEL_MAP.get(request.model_id)
    if not model:
        raise HTTPException(404, "Unknown model.")
    if request.task not in model["tasks"]:
        raise HTTPException(422, "Task is not supported by this model.")
    files = validate_input(request, model)
    config = configurations().get(model["id"], {})
    status, reason = availability(model, config)
    if status != "configured":
        raise HTTPException(503, reason)
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Inference queue is full.")
    id = uuid4().hex
    try:
        with db() as con:
            con.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?)", (id, request.model_id, request.task, "queued", datetime.now(timezone.utc).isoformat(), None, None))
        pool.submit(run, id, request, files, config, config.get("adapter", model.get("builtin_adapter")))
    except Exception:
        slots.release()
        raise
    return {"id": id, "status": "queued"}

@app.get("/v1/jobs/{id}", dependencies=[Depends(authorize)])
def job(id: str):
    with db() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (id,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found.")
    result = {k: row[k] for k in ["id", "model_id", "task", "status", "created_at", "error"]}
    if row["status"] == "completed":
        result["result"] = json.loads(Path(row["result_path"]).read_text(encoding="utf-8"))
    return result

@app.get("/v1/jobs/{id}/result", dependencies=[Depends(authorize)])
def download(id: str):
    with db() as con:
        row = con.execute("SELECT status, result_path FROM jobs WHERE id=?", (id,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found.")
    if row["status"] != "completed":
        raise HTTPException(409, "Result is not available yet.")
    return FileResponse(row["result_path"], media_type="application/json", filename=f"{id}.json")

from backend.workspace import router
from backend import cases
app.include_router(router)
