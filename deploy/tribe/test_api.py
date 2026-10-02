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
