"""One-time deployment restart after admitted inference jobs finish."""
import json,time,subprocess
from pathlib import Path
root=Path("/home/ubuntu/vinicaya-tribe/data")
for _ in range(180):
    busy=False
    for source in root.glob("*/status.json"):
        if json.loads(source.read_text()).get("status") in {"running","queued"}:busy=True;break
    if not busy:
        subprocess.run(["systemctl","restart","vinicaya-tribe"],check=True)
        print("Final API update activated after inference completed.",flush=True)
        break
    time.sleep(10)
else:
    raise SystemExit("API remained busy; no active inference was interrupted. Restart update still pending.")
