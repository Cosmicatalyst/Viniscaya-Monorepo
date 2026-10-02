"""Start the local UI and API together: npm run platform."""
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent.parent
    for port in (3000, 8000):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is already in use. The platform may already be running.")
    node = shutil.which("node")
    if not node: raise SystemExit("Node.js is required.")
    children = []
    try:
        children.append(subprocess.Popen([sys.executable, "-m", "backend.start"], cwd=root))
        children.append(subprocess.Popen([node, str(root / "node_modules/next/dist/bin/next"), "dev"], cwd=root))
        print("Platform: http://127.0.0.1:3000 · API docs: http://127.0.0.1:8000/docs", flush=True)
        while all(child.poll() is None for child in children): time.sleep(1)
    except KeyboardInterrupt: pass
    finally:
        for child in children:
            if child.poll() is None: child.terminate()
        for child in children:
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill()

if __name__ == "__main__": main()
