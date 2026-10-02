"""Local biomedical image/text representations, not diagnostic predictions."""
import json
from pathlib import Path


def infer(request, files, config):
    import open_clip
    import torch
    from PIL import Image
    from transformers import AutoTokenizer
    from backend.adapters.measurements import image_metrics, PATTERNS

    weights = Path(config["weights"])
    text_weights = weights.parent / "pubmedbert"
    settings = json.loads((weights / "open_clip_config.json").read_text())
    settings["model_cfg"]["text_cfg"]["hf_model_name"] = str(text_weights)
    settings["model_cfg"]["text_cfg"]["hf_tokenizer_name"] = str(text_weights)
    local_config = weights / "viniscaya-biomedclip.json"
    local_config.write_text(json.dumps(settings["model_cfg"]), encoding="utf-8")
    open_clip.add_model_config(local_config)
    model, _, preprocess = open_clip.create_model_and_transforms(
        "viniscaya-biomedclip", pretrained=str(weights / "open_clip_pytorch_model.bin"),
        pretrained_text=False, device=config.get("device", "cpu"),
        image_mean=settings["preprocess_cfg"].get("mean"),
        image_std=settings["preprocess_cfg"].get("std"),
    )
    model.eval()
    with Image.open(files[0]) as image:
        if image.width * image.height > 10_000_000:
            raise ValueError("Use a 2D image smaller than 10 megapixels.")
        pixels = preprocess(image.convert("RGB")).unsqueeze(0).to(next(model.parameters()).device)
        quality = image_metrics(image)
    with torch.inference_mode():
        image_vector = model.encode_image(pixels, normalize=True)
        result = {"embedding": image_vector[0].cpu().tolist(), "dimensions": image_vector.shape[-1], "kind": "representation"}
        result["image_quality"] = quality
        category = "Cancer" if request.model_id == "phikon" else "Neurology" if request.model_id == "biomedclip-neurology" else "Radiology"
        candidates = PATTERNS[category]
        tokenizer = AutoTokenizer.from_pretrained(weights, local_files_only=True)
        tokens = tokenizer(["this is a photo of " + prompt for _, prompt in candidates], padding="max_length", truncation=True, max_length=256, return_tensors="pt")["input_ids"].to(pixels.device)
        text_vectors = model.encode_text(tokens, normalize=True)
        scores = (image_vector @ text_vectors.T)[0].cpu().tolist()
        result["candidate_scores"] = sorted([{"label": label, "score": value, "prompt": prompt} for (label, prompt), value in zip(candidates, scores)], key=lambda item: item["score"], reverse=True)
        result["candidate_basis"] = "Exploratory BiomedCLIP prompt similarities (cosine -1 to 1). Candidates are not confirmed findings, calibrated probabilities, or a complete differential. Prompt wording and candidate set affect rankings."
        if request.text:
            tokenizer = AutoTokenizer.from_pretrained(weights, local_files_only=True)
            tokens = tokenizer(request.text, padding="max_length", truncation=True, max_length=256, return_tensors="pt")["input_ids"].to(pixels.device)
            text_vector = model.encode_text(tokens, normalize=True)
            result["image_text_similarity"] = (image_vector @ text_vector.T).item()
        result["note"] = "Biomedical representations and exploratory visual-pattern similarities; no validated diagnostic head."
    return result
