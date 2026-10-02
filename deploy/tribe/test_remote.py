import httpx,json
from pathlib import Path
v=dict(line.split("=",1) for line in Path("api.env").read_text().splitlines() if "=" in line)
with httpx.Client(base_url="http://127.0.0.1:8026",headers={"Authorization":"Bearer "+v["TRIBE_API_TOKEN"]},timeout=30) as client:
 r=client.post("/v1/jobs",data={"text":"A bird sings beside a flowing river. Morning sunlight fills the forest."});r.raise_for_status();Path("test-job.json").write_text(r.text);print(r.text)
