import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from backend import main

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA", tmp_path / "data")
    monkeypatch.setattr(main, "CONFIG", tmp_path / "models.json")
    monkeypatch.setattr(main, "TOKEN", "test-token")
    monkeypatch.setattr(main, "pool", ThreadPoolExecutor(max_workers=1))
    with TestClient(main.app) as client:
        client.headers["Authorization"] = "Bearer test-token"
        yield client

def test_auth_catalog_and_exclusion(client):
    assert client.get("/health").status_code == 200
    assert client.get("/v1/models", headers={"Authorization": "Bearer wrong"}).status_code == 401
    models = client.get("/v1/models").json()["models"]
    assert {m["category"] for m in models} == {"Cancer", "Proteins", "Radiology", "Neurology", "Cardiac", "General"}
    assert not any("medgemma" in m["name"].lower() for m in models)
    assert all(m["status"] == "disabled" for m in models)
    assert all(m["category"] == "Proteins" for m in client.get("/v1/models?category=Proteins").json()["models"])

def test_validation_and_disabled_inference(client):
    assert client.post("/v1/inference", json={"model_id": "esmfold", "task": "structure", "sequence": "BAD123"}).status_code == 422
    assert client.post("/v1/inference", json={"model_id": "esmfold", "task": "structure", "sequence": "ACDEFG"}).status_code == 503
    assert client.post("/v1/inference", json={"model_id": "esmfold", "task": "diagnosis", "sequence": "ACDEFG"}).status_code == 422
    assert client.post("/v1/inference", json={"model_id": "unknown", "task": "embeddings"}).status_code == 404
    assert client.post("/v1/inference", json={"model_id": "phikon", "task": "embeddings"}).status_code == 422

def test_files_and_limits(client, monkeypatch):
    assert client.post("/v1/files", files={"file": ("a.exe", b"x")}).status_code == 415
    assert client.post("/v1/files", files={"file": ("a.png", b"")}).status_code == 400
    monkeypatch.setattr(main, "MAX_UPLOAD", 8)
    assert client.post("/v1/files", files={"file": ("a.png", b"123456789")}).status_code == 413
    uploaded = client.post("/v1/files", files={"file": ("a.png", b"123")})
    assert uploaded.status_code == 201
    id = uploaded.json()["id"]
    assert client.post("/v1/inference", json={"model_id": "phikon", "task": "embeddings", "file_ids": [id]}).status_code == 503
    assert client.post("/v1/inference", json={"model_id": "phikon", "task": "embeddings", "file_ids": ["missing"]}).status_code == 404

def configure():
    main.CONFIG.write_text(json.dumps({"pubmedbert": {"enabled": True, "weights": str(main.DATA), "adapter": "backend.tests.fixture_adapter:infer"}}))

def wait(client, id):
    for _ in range(100):
        job = client.get(f"/v1/jobs/{id}").json()
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(.02)
    pytest.fail("Job did not finish")

def test_real_queue_and_result_download(client):
    configure()
    response = client.post("/v1/inference", json={"model_id": "pubmedbert", "task": "embeddings", "text": "synthetic"})
    assert response.status_code == 202
    id = response.json()["id"]
    job = wait(client, id)
    assert job["status"] == "completed"
    assert job["result"]["output"] == {"length": 9, "test_only": True}
    result = client.get(f"/v1/jobs/{id}/result")
    assert result.status_code == 200
    assert "attachment" in result.headers["content-disposition"]
    report = client.get(f"/v1/jobs/{id}/report")
    assert report.status_code == 200
    assert report.json()["clinical_status"] == "unverified"
    assert "Clinical impression: Indeterminate" in report.json()["markdown"]
    assert client.get(f"/v1/jobs/{id}/report?download=true").headers["content-type"].startswith("text/markdown")
    assert client.get("/v1/jobs/not-found").status_code == 404

def test_adapter_failure_and_missing_weights(client):
    configure()
    id = client.post("/v1/inference", json={"model_id": "pubmedbert", "task": "embeddings", "text": "fail"}).json()["id"]
    assert wait(client, id)["status"] == "failed"
    assert client.get(f"/v1/jobs/{id}/result").status_code == 409
    assert client.get(f"/v1/jobs/{id}/report").status_code == 409
    main.CONFIG.write_text(json.dumps({"esm2": {"enabled": True, "weights": "missing-path"}}))
    assert client.get("/v1/models?category=Proteins").json()["models"][0]["status"] == "missing_weights"

def test_workspace_persistence_and_stats(client):
    id = "a" * 32
    messages = [{"role": "user", "content": "Draft a note"}, {"role": "assistant", "content": "Draft"}]
    assert client.put(f"/v1/threads/{id}", json={"messages": messages}).status_code == 200
    assert client.get(f"/v1/threads/{id}").json()["messages"] == messages
    assert client.get("/v1/stats").json()["threads"] == 1
    configure()
    job = client.post("/v1/inference", json={"model_id": "pubmedbert", "task": "embeddings", "text": "synthetic"}).json()["id"]
    assert wait(client, job)["status"] == "completed"
    assert client.get("/v1/stats").json()["resources"] == 1
    assert client.get("/v1/jobs").json()["jobs"][0]["category"] == "General"
    assert client.put(f"/v1/threads/{id}", json={"messages": [{"role": "system", "content": "bad"}]}).status_code == 422
    assert client.delete(f"/v1/threads/{id}").status_code == 200
    assert client.get(f"/v1/threads/{id}").status_code == 404

def test_cardiac_input_contract(tmp_path):
    import numpy as np
    from backend.adapters.echonext import read_input
    path = tmp_path / "sample.npz"
    np.savez(path, waveforms=np.zeros((1,1,2500,12)), tabular=np.zeros((1,7)))
    assert read_input(path)[0].shape == (1,1,2500,12)
    np.savez(path, waveforms=np.zeros((2,12)), tabular=np.zeros((7,)))
    with pytest.raises(ValueError, match="Expected one ECG"): read_input(path)
    np.savez(path, waveforms=np.full((1,1,2500,12), np.nan), tabular=np.zeros((1,7)))
    with pytest.raises(ValueError, match="finite"): read_input(path)

def test_report_preserves_scores_and_synthetic_scope():
    from backend.reports import compose
    result = {"input": {"files": ["SYNTHETIC.npz"], "synthetic_label": True}, "output": {"predictions": [{"label": "LVEF ≤45%", "score": .123456}]}}
    report = compose({"id": "a"*32, "created_at": "2026-10-02", "model_id": "echonext", "task": "classification"}, result, "Cardiac", "EchoNext")
    assert report["scope"] == "Synthetic test report"
    assert "raw score 0.123456" in report["markdown"]
    assert "not an observed LVEF measurement" in report["markdown"]
    assert "Outputs have no patient-level clinical meaning" in report["markdown"]

def test_quantified_reports_and_supplied_units():
    from backend.adapters.measurements import image_metrics, text_metrics
    from backend.reports import compose
    from PIL import Image
    quality = image_metrics(Image.new("RGB", (100,120), "white"))
    assert quality["intensity_sd"] == 0
    assert {p["label"] for p in quality["problems"]} == {"Small source image", "Low global contrast"}
    text = text_metrics("BP: 120/80 mmHg; HR 78 bpm; SpO2 98%; Temp: 37.2 C; Hb 12.4 g/dL\nAssessment: supplied test problem")
    assert len(text["measurements"]) == 5
    assert text["measurements"][0]["value"] == "120/80"
    assert text["problems"][0]["description"] == "supplied test problem"
    assert text_metrics("HR: 80")["measurements"][0]["unit"] == "not supplied"
    output = {"candidate_scores": [{"label": "Test pattern", "score": .22, "prompt": "test prompt"}], "image_quality": quality, "embedding": [1.,-1.], "dimensions": 2}
    report = compose({"id": "b"*32,"created_at": "2026-10-02","model_id":"phikon","task":"embeddings"},{"output":output},"Cancer","Phikon")
    assert "Test pattern" in report["markdown"]
    assert "0.220000" in report["markdown"]
    assert "not a diagnosis" in report["markdown"]
    assert "Low global contrast" in report["markdown"]

