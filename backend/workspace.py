"""Persistent workspace and OpenAI-compatible local streaming chat."""
import json
import queue
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
from backend import main
from backend.catalog import MODEL_MAP

router = APIRouter(dependencies=[Depends(main.authorize)])

@router.get("/v1/jobs/{id}/report")
def report(id: str, download: bool = False):
    from pathlib import Path
    from backend.reports import compose
    with main.db() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (id,)).fetchone()
    if not row: raise HTTPException(404, "Analysis not found.")
    if row["status"] != "completed": raise HTTPException(409, "Complete the analysis before generating a report.")
    model = MODEL_MAP.get(row["model_id"], {})
    result = json.loads(Path(row["result_path"]).read_text(encoding="utf-8"))
    document = result.get("case_report") or compose(dict(row), result, model.get("category", "General"), model.get("name", row["model_id"]))
    from backend.groq_reports import ensure
    with main.db() as con:
        files = [con.execute("SELECT name,path FROM files WHERE id=?", (file_id,)).fetchone() for file_id in result.get("input", {}).get("file_ids", [])]
    document = ensure(id, document, result.get("report_assets", [(file["name"], file["path"]) for file in files if file]))
    if download:
        return Response(document["markdown"], media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="analysis-{row["id"]}.md"'})
    return document

@router.post("/v1/jobs/{id}/report")
def retry_report(id: str):
    from pathlib import Path
    from backend.groq_reports import ensure
    from backend.reports import compose
    with main.db() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (id,)).fetchone()
    if not row: raise HTTPException(404, "Analysis not found.")
    if row["status"] != "completed": raise HTTPException(409, "Analysis is incomplete.")
    result = json.loads(Path(row["result_path"]).read_text(encoding="utf-8"))
    model = MODEL_MAP.get(row["model_id"], {})
    original = result.get("case_report") or compose(dict(row), result, model.get("category", "General"), model.get("name", row["model_id"]))
    with main.db() as con:
        files = [con.execute("SELECT name,path FROM files WHERE id=?", (file_id,)).fetchone() for file_id in result.get("input", {}).get("file_ids", [])]
    return ensure(id, original, result.get("report_assets", [(file["name"], file["path"]) for file in files if file]), retry=True)

@router.get("/v1/jobs/{id}/segmentation")
def segmentation(id: str):
    from pathlib import Path
    from fastapi.responses import FileResponse
    with main.db() as con:
        row = con.execute("SELECT status,result_path FROM jobs WHERE id=?", (id,)).fetchone()
    if not row: raise HTTPException(404, "Analysis not found.")
    if row["status"] != "completed": raise HTTPException(409, "Analysis is incomplete.")
    result = json.loads(Path(row["result_path"]).read_text(encoding="utf-8"))
    candidates = [item.get("mask_file") for source in result.get("output", {}).get("sources", []) for item in source.get("outputs", []) if item.get("mask_file")]
    if result.get("output", {}).get("mask_file"): candidates.append(result["output"]["mask_file"])
    root = (main.DATA / "results" / f"{id}-assets").resolve()
    for candidate in candidates:
        path = Path(candidate).resolve()
        if path.is_relative_to(root) and path.is_file(): return FileResponse(path, media_type="application/gzip", filename="predicted-brain-regions.nii.gz")
    raise HTTPException(404, "No predicted segmentation is available for this analysis.")

@router.get("/v1/jobs/{id}/chat-context")
def chat_context(id: str):
    from pathlib import Path
    from backend.groq_reports import read
    with main.db() as con: row = con.execute("SELECT * FROM jobs WHERE id=?", (id,)).fetchone()
    if not row: raise HTTPException(404, "Attached analysis not found.")
    if row["status"] != "completed": raise HTTPException(409, "Attached analysis is not complete.")
    result=json.loads(Path(row["result_path"]).read_text(encoding="utf-8"))
    def compact(value):
        if isinstance(value,dict):
            cleaned={k:compact(v) for k,v in value.items() if k not in {"embedding","pdb","mask_file"}}
            if isinstance(value.get("predictions"),list): cleaned["prediction_count"]=len(value["predictions"])
            return cleaned
        if isinstance(value,list): return [compact(item) for item in value]
        return value
    generated=read(id)
    report_text=generated["markdown"] if generated and generated.get("generation_status")=="completed" else "Final report unavailable; use measured outputs only."
    raw=json.dumps(compact(result.get("output",{})),ensure_ascii=False)
    context="Analysis ID: "+id+"\nUnsigned report:\n"+report_text[:14000]+"\nMeasured model outputs:\n"+raw[:12000]
    if len(report_text)>14000 or len(raw)>12000: context+="\nContext was truncated. Full raw data remains available in the analysis; omitted details cannot be assumed."
    return {"id":id,"title":MODEL_MAP.get(row["model_id"],{}).get("category","Analysis")+" report","context":context}

@router.get("/v1/files/{id}/preview")
def file_preview(id: str):
    import base64, io
    from pathlib import Path
    from PIL import Image
    from backend.cases import extract
    with main.db() as con: row=con.execute("SELECT * FROM files WHERE id=?",(id,)).fetchone()
    if not row: raise HTTPException(404,"Source file not found.")
    path=Path(row["path"])
    folder=main.DATA/"previews"/id
    folder.mkdir(parents=True,exist_ok=True)
    try:
        if path.suffix.lower()==".npz":
            import numpy as np,zipfile
            with zipfile.ZipFile(path) as archive:
                if sum(item.file_size for item in archive.infolist())>32*1024*1024: raise ValueError("Numeric preview exceeds size limit.")
            with np.load(path,allow_pickle=False) as data:
                waves=data["waveforms"]
                if waves.shape!=(1,1,2500,12) or not np.isfinite(waves).all(): raise ValueError("Waveform preview needs finite EchoNext waveform shape (1,1,2500,12).")
                traces=waves[0,0,::10,:].T.tolist()
                return {"name":row["name"],"images":[],"text":"Prepared ECG array; lead order and physical units are not independently verified.","waveforms":traces}
        previews,text,notes=extract(path,row["name"],folder,"preview")
        images=[]
        for label,filename in previews:
            with Image.open(filename) as source:
                image=source.convert("RGB");image.thumbnail((768,768));buffer=io.BytesIO();image.save(buffer,format="PNG")
                images.append({"label":label,"src":"data:image/png;base64,"+base64.b64encode(buffer.getvalue()).decode()})
        return {"name":row["name"],"images":images,"text":text,"coverage":notes}
    except Exception as error:
        raise HTTPException(422,str(error)[:250] if isinstance(error,ValueError) else "Preview could not be decoded. This file has not been visually assessed.")

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)

class ThreadBody(BaseModel):
    report_ids: list[str] = Field(default_factory=list, max_length=4)
    messages: list[Message] = Field(min_length=1, max_length=40)

class ChatBody(ThreadBody):
    model: Literal["qwen-small"] = "qwen-small"
    stream: bool = True
    max_tokens: int = Field(default=384, ge=1, le=512)

def validate_messages(body):
    if sum(len(m.content) for m in body.messages) > 60000:
        raise HTTPException(422, "Conversation is too long.")

@router.get("/v1/threads")
def threads():
    with main.db() as con:
        rows = con.execute("SELECT id,title,updated_at FROM threads ORDER BY updated_at DESC LIMIT 200").fetchall()
    return {"threads": [dict(row) for row in rows]}

@router.get("/v1/threads/{id}")
def thread(id: str):
    with main.db() as con:
        row = con.execute("SELECT * FROM threads WHERE id=?", (id,)).fetchone()
    if not row: raise HTTPException(404, "Thread not found.")
    return {**dict(row), "messages": json.loads(row["messages"]), "report_ids": json.loads(row["report_ids"])}

@router.put("/v1/threads/{id}")
def save_thread(id: str, body: ThreadBody):
    if len(id) != 32 or any(c not in "0123456789abcdef" for c in id): raise HTTPException(422, "Invalid thread ID.")
    validate_messages(body)
    for report_id in body.report_ids:
        chat_context(report_id)
    title = next((m.content for m in body.messages if m.role == "user"), "Conversation")[:80]
    now = datetime.now(timezone.utc).isoformat()
    with main.db() as con:
        con.execute("INSERT INTO threads (id,title,messages,updated_at,report_ids) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,messages=excluded.messages,updated_at=excluded.updated_at,report_ids=excluded.report_ids", (id, title, json.dumps([m.model_dump() for m in body.messages]), now, json.dumps(body.report_ids)))
    return {"id": id, "title": title, "updated_at": now}

@router.delete("/v1/threads/{id}")
def remove_thread(id: str):
    with main.db() as con: con.execute("DELETE FROM threads WHERE id=?", (id,))
    return {"deleted": id}

@router.get("/v1/jobs")
def jobs():
    with main.db() as con:
        rows = con.execute("SELECT id,model_id,task,status,created_at,error FROM jobs ORDER BY created_at DESC LIMIT 200").fetchall()
    return {"jobs": [dict(row) | {"category": MODEL_MAP.get(row["model_id"], {}).get("category", "General")} for row in rows]}

@router.get("/v1/stats")
def stats():
    with main.db() as con:
        count = con.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
        rows = con.execute("SELECT model_id,status,created_at FROM jobs").fetchall()
        conversations = con.execute("SELECT updated_at FROM threads").fetchall()
    dates = [(datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat() for i in reversed(range(7))]
    completed = [r for r in rows if r["status"] == "completed"]
    return {"threads": count, "resources": len(completed), "analyses": len(rows), "activity": [{"date": day, "analyses": sum(r["created_at"][:10] == day for r in rows), "threads": sum(r["updated_at"][:10] == day for r in conversations)} for day in dates], "specialties": [{"name": name, "count": sum(MODEL_MAP.get(r["model_id"], {}).get("category") == name for r in completed)} for name in ["Cancer", "Proteins", "Radiology", "Neurology", "Cardiac", "General"]]}

@router.post("/v1/chat/completions")
def chat(body: ChatBody):
    validate_messages(body)
    config = main.configurations().get("qwen-small", {})
    status, reason = main.availability(MODEL_MAP["qwen-small"], config)
    if status != "configured": raise HTTPException(503, reason)
    if not main.slots.acquire(blocking=False): raise HTTPException(429, "Local inference queue is full.")
    events = queue.Queue()
    stop = threading.Event()
    def generate():
        try:
            import torch
            from transformers import TextStreamer, StoppingCriteria, StoppingCriteriaList
            from backend.adapters.text import load, inputs_for, SYSTEM
            tokenizer, model = load(config["weights"], config.get("device", "cpu"))
            class Streamer(TextStreamer):
                def on_finalized_text(self, text, stream_end=False):
                    if text: events.put(("token", text))
                    if stream_end: events.put(("done", ""))
            class Cancel(StoppingCriteria):
                def __call__(self, input_ids, scores, **kwargs): return stop.is_set()
            inputs = inputs_for(tokenizer, model, [{"role": "system", "content": SYSTEM}, *[m.model_dump() for m in body.messages]])
            with torch.inference_mode():
                model.generate(**inputs, max_new_tokens=body.max_tokens, do_sample=False, pad_token_id=tokenizer.eos_token_id, streamer=Streamer(tokenizer, skip_prompt=True, skip_special_tokens=True), stopping_criteria=StoppingCriteriaList([Cancel()]))
        except Exception as error:
            events.put(("error", str(error) if isinstance(error, ValueError) else "Local text generation failed."))
        finally:
            main.slots.release()
    try: main.pool.submit(generate)
    except Exception:
        main.slots.release()
        raise
    def stream():
        deadline = time.monotonic() + 180
        try:
            while time.monotonic() < deadline:
                try: kind, text = events.get(timeout=3)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                if kind == "done":
                    yield "data: [DONE]\n\n"
                    return
                data = {"choices": [{"delta": {"content": text}}]} if kind == "token" else {"error": text}
                yield "data: " + json.dumps(data) + "\n\n"
                if kind == "error": return
            yield 'data: {"error":"Generation timed out."}\n\n'
        finally: stop.set()
    if body.stream: return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    content = ""
    for event in stream():
        if event.startswith("data: {"):
            data = json.loads(event[6:])
            if "error" in data: raise HTTPException(503, data["error"])
            content += data["choices"][0]["delta"]["content"]
    return {"id": uuid4().hex, "model": "qwen-small", "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]}
