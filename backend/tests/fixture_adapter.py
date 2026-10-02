"""Synthetic adapter used only to exercise job infrastructure in tests."""
def infer(request, files, config):
    if request.text == "fail":
        raise RuntimeError("test failure")
    return {"length": len(request.text or ""), "test_only": True}
