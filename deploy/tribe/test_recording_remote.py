import subprocess,httpx,json,time
from pathlib import Path
subprocess.run(["ffmpeg","-y","-v","error","-i","data/50dc4b8c00ad4803bb681ac0f74ecc4c/speech.wav","-c:a","libopus","test-recording.webm"],check=True)
v=dict(line.split("=",1) for line in Path("api.env").read_text().splitlines() if "=" in line)
with httpx.Client(base_url="http://127.0.0.1:8026",headers={"Authorization":"Bearer "+v["TRIBE_API_TOKEN"]},timeout=30) as c:
 with open("test-recording.webm","rb") as f:r=c.post("/v1/jobs",files={"file":("voice.webm",f,"audio/webm")})
 r.raise_for_status();id=r.json()["id"];print("submitted",id,flush=True)
 for _ in range(24):
  time.sleep(2);j=c.get("/v1/jobs/"+id).json()
  if j["status"] in {"completed","failed"}:
   print(j["status"],j.get("error"),j.get("result",{}).get("shape"));break
