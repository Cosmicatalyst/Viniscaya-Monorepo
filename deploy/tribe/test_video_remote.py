import subprocess,httpx
from pathlib import Path
subprocess.run(["ffmpeg","-y","-f","lavfi","-i","testsrc=size=320x240:rate=16","-i","data/50dc4b8c00ad4803bb681ac0f74ecc4c/speech.wav","-t","5","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","test-stimulus.mp4"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
v=dict(line.split("=",1) for line in Path("api.env").read_text().splitlines() if "=" in line)
with httpx.Client(base_url="http://127.0.0.1:8026",headers={"Authorization":"Bearer "+v["TRIBE_API_TOKEN"]},timeout=30) as c:
 with open("test-stimulus.mp4","rb") as f:r=c.post("/v1/jobs",files={"file":("test-stimulus.mp4",f,"video/mp4")})
 r.raise_for_status();Path("test-video-job.json").write_text(r.text);print(r.text)
