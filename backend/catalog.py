"""One selected local research model per specialty; no clinical validation implied."""
def model(id, name, category, modality, tasks, adapter=None):
    return dict(id=id, name=name, category=category, modality=modality, tasks=tasks, builtin_adapter=adapter)

MODELS = [
    model("phikon", "Phikon", "Cancer", "image", ["embeddings"], "backend.adapters.hf:infer"),
    model("esm2", "ESM-2 150M", "Proteins", "sequence", ["embeddings"], "backend.adapters.esm2:infer"),
    model("esmfold", "ESMFold", "Proteins", "sequence", ["structure"], "backend.adapters.esmfold:infer"),
    model("medsiglip-radiology", "MedSigLIP-448", "Radiology", "image_text", ["embeddings", "retrieval"], "backend.adapters.medsiglip:infer"),
    model("xrv-chest", "TorchXRayVision DenseNet121", "Radiology", "image", ["classification"], "backend.adapters.xrv:infer"),
    model("medsiglip-neurology", "MedSigLIP-448", "Neurology", "image_text", ["embeddings"], "backend.adapters.medsiglip:infer"),
    model("brats-mri", "MONAI BraTS SegResNet", "Neurology", "volume", ["segmentation"], "backend.adapters.brats:infer"),
    model("echonext", "EchoNext", "Cardiac", "signal", ["classification"], "backend.adapters.echonext:infer"),
    model("qwen-small", "Qwen2.5 0.5B", "General", "text", ["question_answering"], "backend.adapters.text:infer"),
    model("pubmedbert", "PubMedBERT", "General", "text", ["embeddings"], "backend.adapters.hf:infer"),
]
MODEL_MAP = {m["id"]: m for m in MODELS}

# Historical jobs remain readable without offering replaced encoders for new cases.
for category in ["Radiology", "Neurology"]:
    id = "biomedclip-" + category.lower()
    MODEL_MAP[id] = model(id, "BiomedCLIP", category, "image_text", ["embeddings"], "backend.adapters.biomedclip:infer")

