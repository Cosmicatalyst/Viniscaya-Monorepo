"""Authenticated research brain-response API; one stimulus per job."""
import os, json, secrets, threading, subprocess
from pathlib import Path
from uuid import uuid4
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import HTTPBearer
from fastapi.responses import FileResponse

ROOT=Path(os.getenv("TRIBE_DATA_DIR", "data"));ROOT.mkdir(parents=True,exist_ok=True)
TOKEN=os.environ["TRIBE_API_TOKEN"]
@asynccontextmanager
async def lifespan(app):
    for path in ROOT.glob("*/status.json"):
        previous=json.loads(path.read_text())
        if previous.get("status") in {"queued","running"}:
            previous.update(status="failed",error="Service restarted before inference completed. Submit the stimulus again.")
            status(path.parent,previous)
    yield

app=FastAPI(title="Vinicaya TRIBE v2 Research API",lifespan=lifespan)
auth=HTTPBearer();pool=ThreadPoolExecutor(max_workers=1);slots=threading.BoundedSemaphore(2)
model=None

def authorize(credentials=Depends(auth)):
    if not secrets.compare_digest(credentials.credentials,TOKEN):raise HTTPException(401,"Invalid API token")

def folder(id):
    if len(id)!=32 or any(c not in "0123456789abcdef" for c in id):raise HTTPException(404,"Unknown job")
    path=ROOT/id
    if not (path/"status.json").is_file():raise HTTPException(404,"Unknown job")
    return path

def status(path,value):
    temporary=path/"status.tmp";temporary.write_text(json.dumps(value),encoding="utf-8");temporary.replace(path/"status.json")

@app.get("/health")
def health():return {"status":"ok","service":"TRIBE v2","model_loaded":model is not None,"clinical_use":False}

def transcribe(filename, language):
    import pandas as pd
    from transformers import pipeline
    recognizer=pipeline("automatic-speech-recognition",model="openai/whisper-small",device=-1)
    transcript=recognizer(str(filename),return_timestamps="word",generate_kwargs={"language":"english"})
    rows=[]
    for item in transcript["chunks"]:
        start,end=item["timestamp"]
        if start is None or end is None:continue
        rows.append({"text":item["text"].strip(),"start":float(start),"duration":float(end-start),"sequence_id":0,"sentence":transcript["text"]})
    if not rows:raise ValueError("No timed words could be extracted from the stimulus")
    return pd.DataFrame(rows)

def run(path,id,source,kind):
    global model
    try:
        status(path,{"id":id,"status":"running","phase":"Loading model"})
        import numpy as np
        from tribev2 import TribeModel
        if model is None:
            model=TribeModel.from_pretrained(os.getenv("TRIBE_WEIGHTS", "facebook/tribev2"),cache_folder=str(ROOT/"cache"),device="cpu",config_update={"data.text_feature.device":"cpu","data.audio_feature.device":"cpu","data.image_feature.image.device":"cpu","data.video_feature.image.device":"cpu","data.batch_size":1})
        status(path,{"id":id,"status":"running","phase":"Preparing stimulus and word timings"})
        if kind=="text":
            audio=path/"speech.wav"
            subprocess.run(["espeak-ng","-f",str(source),"-w",str(audio)],check=True,timeout=60)
            source=audio;kind="audio"
        duration=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(source)],timeout=30,text=True).strip()
        if not duration or float(duration)>120:raise ValueError("Use a stimulus lasting at most 120 seconds")
        from tribev2.eventstransforms import ExtractWordsFromAudio
        ExtractWordsFromAudio._get_transcript_from_audio=staticmethod(transcribe)
        events=model.get_events_dataframe(**{kind+"_path":str(source)})
        status(path,{"id":id,"status":"running","phase":"Encoding stimulus and predicting cortical responses"})
        predictions,segments=model.predict(events,verbose=False)
        if predictions.ndim!=2 or not len(predictions) or not np.isfinite(predictions).all():raise ValueError("Model returned unusable predictions")
        np.save(path/"predictions.npy",predictions,allow_pickle=False)
        timeline=[{"start_seconds":float(segment.start),"duration_seconds":float(segment.duration),"mean_response":float(row.mean()),"rms_response":float(np.sqrt((row**2).mean()))} for row,segment in zip(predictions,segments)]
        result={"model":"TRIBE v2","shape":list(predictions.shape),"surface":"fsaverage5","timeline":timeline,"note":"Predicted average-subject cortical responses to this stimulus. Not measured patient brain activity, diagnosis, EEG or tumor analysis. Summary means/RMS are visualization statistics, not clinical metrics. Text is locally synthesized with espeak-ng; word timings use Whisper-small in place of upstream WhisperX. This preprocessing variant has not been benchmarked."}
        (path/"result.json").write_text(json.dumps(result,allow_nan=False),encoding="utf-8")
        status(path,{"id":id,"status":"completed"})
    except Exception as error:
        import logging
        logging.exception("TRIBE inference failed")
        status(path,{"id":id,"status":"failed","error":str(error)[:250] if isinstance(error,ValueError) else "Inference failed; model dependencies or access may be unavailable. Check server logs."})
    finally:slots.release()

@app.post("/v1/jobs",status_code=202,dependencies=[Depends(authorize)])
async def submit(file:UploadFile|None=File(None),text:str=Form("")):
    if bool(file)==bool(text.strip()):raise HTTPException(422,"Provide exactly one text, audio or video stimulus")
    suffix=Path(file.filename or "").suffix.lower() if file else ".txt"
    kinds={".txt":"text",".wav":"audio",".mp3":"audio",".flac":"audio",".ogg":"audio",".mp4":"video",".avi":"video",".mkv":"video",".mov":"video",".webm":"video"}
    if suffix not in kinds:raise HTTPException(422,"Unsupported stimulus format")
    if len(text)>5000:raise HTTPException(422,"Text limit is 5000 characters")
    if not slots.acquire(False):raise HTTPException(429,"Inference queue is full")
    id=uuid4().hex;path=ROOT/id;path.mkdir();source=path/("stimulus"+suffix)
    try:
        if file:
            size=0
            with source.open("wb") as stream:
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk)
                    if size>25*1024*1024:raise HTTPException(413,"Upload limit is 25 MB")
                    stream.write(chunk)
            if not size:raise HTTPException(422,"Empty upload")
        else:source.write_text(text,encoding="utf-8")
        status(path,{"id":id,"status":"queued"});pool.submit(run,path,id,source,kinds[suffix])
    except Exception:slots.release();raise
    return {"id":id,"status":"queued"}

@app.get("/v1/jobs/{id}",dependencies=[Depends(authorize)])
def job(id:str):
    path=folder(id);result=json.loads((path/"status.json").read_text())
    if result["status"]=="completed":result["result"]=json.loads((path/"result.json").read_text())
    return result

@app.get("/v1/jobs/{id}/predictions",dependencies=[Depends(authorize)])
def predictions(id:str):
    path=folder(id)
    if not (path/"predictions.npy").is_file():raise HTTPException(409,"Predictions not ready")
    return FileResponse(path/"predictions.npy",filename="tribe-brain-responses.npy",media_type="application/octet-stream")
