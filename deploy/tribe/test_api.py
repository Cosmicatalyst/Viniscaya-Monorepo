import os, importlib.util
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv("TRIBE_API_TOKEN","test-token")
    monkeypatch.setenv("TRIBE_DATA_DIR",str(tmp_path))
    spec=importlib.util.spec_from_file_location("tribe_test_api",Path(__file__).with_name("api.py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    class Queue:
        def submit(self,*args):return None
    module.pool=Queue()
    return TestClient(module.app)

def test_auth_and_validation(client):
    assert client.get("/health").status_code==200
    assert client.post("/v1/jobs",data={"text":"hello"}).status_code==401
    headers={"Authorization":"Bearer test-token"}
    assert client.post("/v1/jobs",headers=headers).status_code==422
    assert client.post("/v1/jobs",headers=headers,data={"text":"A"*5001}).status_code==422
    assert client.post("/v1/jobs",headers=headers,files={"file":("bad.exe",b"bad")}).status_code==422
    assert client.post("/v1/jobs",headers=headers,data={"text":"hello"},files={"file":("clip.wav",b"test")}).status_code==422

def test_queue_and_raw_download_guard(client):
    headers={"Authorization":"Bearer test-token"}
    r=client.post("/v1/jobs",headers=headers,data={"text":"hello"});assert r.status_code==202
    id=r.json()["id"]
    assert client.get("/v1/jobs/"+id,headers=headers).json()["status"]=="queued"
    assert client.get("/v1/jobs/"+id+"/predictions",headers=headers).status_code==409
    assert client.post("/v1/jobs",headers=headers,data={"text":"hello"}).status_code==202
    assert client.post("/v1/jobs",headers=headers,data={"text":"hello"}).status_code==429


def test_brain_frame_auth_and_bounds(client):
    import numpy as np,json
    headers={"Authorization":"Bearer test-token"}
    id=client.post("/v1/jobs",headers=headers,data={"text":"hello"}).json()["id"]
    assert client.get(f"/v1/jobs/{id}/frames/0").status_code==401
    assert client.get(f"/v1/jobs/{id}/frames/0",headers=headers).status_code==409
    path=Path(os.environ["TRIBE_DATA_DIR"])/id
    (path/"status.json").write_text(json.dumps({"id":id,"status":"completed"}),encoding="utf-8")
    np.save(path/"predictions.npy",np.zeros((2,20484)),allow_pickle=False)
    assert client.get(f"/v1/jobs/{id}/frames/2",headers=headers).status_code==404
    assert client.get(f"/v1/jobs/{id}/frames/-1",headers=headers).status_code==404


def test_microphone_webm_is_audio(client,monkeypatch):
    # Capture worker arguments without running heavyweight inference.
    endpoint=next(route.endpoint for route in client.app.routes if getattr(route,"path",None)=="/v1/jobs")
    captured=[]
    class Queue:
        def submit(self,*args):captured.append(args)
    monkeypatch.setitem(endpoint.__globals__,"pool",Queue())
    response=client.post("/v1/jobs",headers={"Authorization":"Bearer test-token"},files={"file":("voice.webm",b"recording","audio/webm")})
    assert response.status_code==202
    assert captured[0][-1]=="audio"
