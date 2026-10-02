"""Launch from the project root: backend/.venv/Scripts/python.exe -m backend.start"""
import os
from pathlib import Path
import uvicorn

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

root = Path(__file__).resolve().parent.parent
env = root / ".env.local"
if env.exists():
    for line in env.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            if key.strip() in {"MEDICAL_API_TOKEN", "GROQ_API_KEY"}:
                os.environ.setdefault(key.strip(), value.strip())

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000)
