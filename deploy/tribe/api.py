"""Authenticated research brain-response API; one stimulus per job."""
import os, json, secrets, threading, subprocess, time
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
recognizer=None
video_optimized=False

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
    global recognizer
    import pandas as pd
    import torch
    from transformers import pipeline
    if recognizer is None:
        gpu=os.getenv("TRIBE_DEVICE","cpu")=="cuda" and torch.cuda.is_available()
        recognizer=pipeline("automatic-speech-recognition",model="openai/whisper-small",device=0 if gpu else -1,torch_dtype=torch.float16 if gpu else torch.float32)
    transcript=recognizer(str(filename),return_timestamps="word",generate_kwargs={"language":"english"})
    rows=[]
    for item in transcript["chunks"]:
        start,end=item["timestamp"]
        if start is None or end is None:continue
        rows.append({"text":item["text"].strip(),"start":float(start),"duration":float(end-start),"sequence_id":0,"sentence":transcript["text"]})
    if not rows:raise ValueError("No timed words could be extracted from the stimulus")
    return pd.DataFrame(rows)

def run(path,id,source,kind):
    global model, video_optimized
    started=time.monotonic()
    try:
        status(path,{"id":id,"status":"running","phase":"Loading model"})
        import numpy as np
        import torch
        from tribev2 import TribeModel
        device=os.getenv("TRIBE_DEVICE","cpu")
        if device=="cuda":
            if not torch.cuda.is_available():raise ValueError("GPU runtime is unavailable")
            torch.cuda.set_per_process_memory_fraction(0.28)
            torch.backends.cuda.matmul.allow_tf32=True
            torch.backends.cudnn.allow_tf32=True
            if not video_optimized:
                from neuralset.extractors.video import _HFVideoModel
                original=_HFVideoModel.predict_hidden_states
                def fast_hidden_states(self,images,audio=None):
                    with torch.autocast("cuda",dtype=torch.bfloat16,enabled=self.model.device.type=="cuda"):
                        return original(self,images,audio).float()
                _HFVideoModel.predict_hidden_states=fast_hidden_states
                video_optimized=True
        if model is None:
            model=TribeModel.from_pretrained(os.getenv("TRIBE_WEIGHTS", "facebook/tribev2"),cache_folder=str(ROOT/"cache"),device=device,config_update={"data.text_feature.device":device,"data.audio_feature.device":device,"data.image_feature.image.device":device,"data.video_feature.image.device":device,"data.video_feature.image.batch_size":1,"data.batch_size":1})
        status(path,{"id":id,"status":"running","phase":"Preparing stimulus and word timings"})
        if kind=="text":
            audio=path/"speech.wav"
            subprocess.run(["espeak-ng","-f",str(source),"-w",str(audio)],check=True,timeout=60)
            source=audio;kind="audio"
        if kind=="audio" and source.suffix.lower()!=".wav":
            decoded=path/"decoded-audio.wav"
            subprocess.run(["ffmpeg","-y","-v","error","-i",str(source),"-vn","-t","121","-ac","1","-ar","16000",str(decoded)],check=True,timeout=120)
            source=decoded
        duration=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(source)],timeout=30,text=True).strip()
        if not duration or float(duration)>120:raise ValueError("Use a stimulus lasting at most 120 seconds")
        from tribev2.eventstransforms import ExtractWordsFromAudio
        ExtractWordsFromAudio._get_transcript_from_audio=staticmethod(transcribe)
        prepared=time.monotonic()
        events=model.get_events_dataframe(**{kind+"_path":str(source)})
        status(path,{"id":id,"status":"running","phase":"Encoding stimulus and predicting cortical responses"})
        encoded=time.monotonic()
        predictions,segments=model.predict(events,verbose=False)
        if predictions.ndim!=2 or not len(predictions) or not np.isfinite(predictions).all():raise ValueError("Model returned unusable predictions")
        np.save(path/"predictions.npy",predictions,allow_pickle=False)
        timeline=[{"start_seconds":float(segment.start),"duration_seconds":float(segment.duration),"mean_response":float(row.mean()),"rms_response":float(np.sqrt((row**2).mean()))} for row,segment in zip(predictions,segments)]
        result={"model":"TRIBE v2","shape":list(predictions.shape),"surface":"fsaverage5","timings_seconds":{"preparation":round(prepared-started,2),"word_timings":round(encoded-prepared,2),"prediction":round(time.monotonic()-encoded,2),"total":round(time.monotonic()-started,2)},"timeline":timeline,"note":"Predicted average-subject cortical responses to this stimulus. Not measured patient brain activity, diagnosis, EEG or tumor analysis. Summary means/RMS are visualization statistics, not clinical metrics. Text is locally synthesized with espeak-ng; word timings use Whisper-small in place of upstream WhisperX. GPU video encoding uses bfloat16 mixed precision; small numerical differences are possible. This preprocessing variant has not been benchmarked."}
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
    if file and suffix in {".webm",".mp4"} and (file.content_type or "").startswith("audio/"):kinds[suffix]="audio"
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


plot_lock=threading.Lock()
@app.get("/v1/jobs/{id}/frames/{step}",dependencies=[Depends(authorize)])
def brain_frame(id:str,step:int):
    path=folder(id)
    if json.loads((path/"status.json").read_text())["status"]!="completed":raise HTTPException(409,"Predictions not ready")
    import numpy as np
    data=np.load(path/"predictions.npy",mmap_mode="r",allow_pickle=False)
    if not 0<=step<len(data):raise HTTPException(404,"Unknown time step")
    if data.shape[1]!=20484:raise HTTPException(422,"Unsupported cortical surface")
    image=path/f"brain-{step}.png"
    with plot_lock:
        if not image.exists():
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from nilearn import datasets, plotting
            mesh=datasets.fetch_surf_fsaverage("fsaverage5")
            limit=max(float(np.percentile(np.abs(data),98)),1e-6)
            fig=plt.figure(figsize=(10,3.5),facecolor="white")
            try:
                for i,hemi in enumerate(("left","right")):
                    ax=fig.add_subplot(1,2,i+1,projection="3d")
                    plotting.plot_surf_stat_map(mesh[f"infl_{hemi}"],data[step,i*10242:(i+1)*10242],hemi=hemi,view="lateral",bg_map=mesh[f"sulc_{hemi}"],cmap="cold_hot",vmin=-limit,vmax=limit,colorbar=i==1,axes=ax,figure=fig,title=f"{hemi.title()} cortex")
                fig.savefig(image,dpi=120,bbox_inches="tight")
            finally:plt.close(fig)
    return FileResponse(image,media_type="image/png")


@app.get("/v1/jobs/{id}/report",dependencies=[Depends(authorize)])
def brain_report(id:str,download:bool=False):
    path=folder(id)
    if json.loads((path/"status.json").read_text())["status"]!="completed":raise HTTPException(409,"Predictions not ready")
    import numpy as np
    result=json.loads((path/"result.json").read_text())
    data=np.load(path/"predictions.npy",mmap_mode="r",allow_pickle=False)
    points=result["timeline"]
    peak=max(points,key=lambda p:p["rms_response"])
    rms=np.array([p["rms_response"] for p in points])
    mean=np.array([p["mean_response"] for p in points])
    left=float(np.sqrt(np.mean(np.square(data[:,:10242]))))
    right=float(np.sqrt(np.mean(np.square(data[:,10242:]))))
    rows="\n".join(f"| {p['start_seconds']:.2f} | {p['duration_seconds']:.2f} | {p['mean_response']:.5f} | {p['rms_response']:.5f} |" for p in points)
    markdown=f"""# Brain-response research report
Analysis: `{id}` · Model: TRIBE v2

## Scope
Predicted average-subject cortical response to the submitted stimulus. This is a model-generated response sequence, not a recording of the speaker's or patient's brain activity.

## Quantitative summary
- Time steps: **{data.shape[0]}**; cortical vertices: **{data.shape[1]:,}** (fsaverage5).
- Modeled window: **{points[0]['start_seconds']:.2f}–{points[-1]['start_seconds']+points[-1]['duration_seconds']:.2f} seconds**.
- Peak global RMS: **{peak['rms_response']:.5f}** at **{peak['start_seconds']:.2f} seconds**.
- Global RMS range: **{rms.min():.5f}–{rms.max():.5f}**; average **{rms.mean():.5f}**.
- Signed mean response range: **{mean.min():.5f}–{mean.max():.5f}**.
- Whole-sequence hemisphere RMS: left **{left:.5f}**, right **{right:.5f}**.

## Interpretation
The largest modeled overall response occurs at {peak['start_seconds']:.2f} seconds. Global RMS summarizes magnitude across vertices; the signed mean can cancel opposing responses. Hemisphere RMS compares overall modeled magnitude and does not establish functional lateralization, abnormality, or disease. Values are in model units, with no validated clinical reference range.

## Cortical maps
The timeline-linked maps show left and right lateral cortical surfaces. Warm and cool colors represent positive and negative model values; neither indicates healthy or diseased tissue. All frames share the same scale. Lateral views do not expose every cortical region.

## Temporal measurements
| Start (s) | Window (s) | Signed mean | RMS |
| --- | --- | --- | --- |
{rows}

## Limits and next steps
{result['note']}

No EEG, fMRI, examination, or clinical history was measured in this analysis. Disease, cognition, emotion, and neurological function cannot be determined from these predictions. Compare stimulus-aligned predictions with recorded brain measurements in a validated research protocol before drawing individual conclusions.
"""
    if download:
        from fastapi.responses import Response
        return Response(markdown,media_type="text/markdown",headers={"Content-Disposition":f'attachment; filename="brain-response-{id}.md"'})
    return {"title":"Brain-response report","scope":"Predicted cortical activity · Research interpretation","markdown":markdown,"generation_status":"completed","model":"TRIBE v2"}
