"""Optional local-only Transformers adapters. No automatic model downloads."""
from functools import lru_cache

@lru_cache(maxsize=1)
def load(model_id, weights, device, task):
    import torch
    from transformers import AutoTokenizer, AutoModel, AutoModelForCausalLM, AutoImageProcessor
    if model_id == "phikon":
        processor = AutoImageProcessor.from_pretrained(weights, local_files_only=True)
        model = AutoModel.from_pretrained(weights, local_files_only=True).to(device).eval()
    else:
        processor = AutoTokenizer.from_pretrained(weights, local_files_only=True)
        cls = AutoModelForCausalLM if task == "question_answering" else AutoModel
        model = cls.from_pretrained(weights, local_files_only=True).to(device).eval()
    return processor, model

def infer(request, files, config):
    import torch
    from backend.adapters.measurements import image_metrics, text_metrics
    quality = None
    processor, model = load(request.model_id, config["weights"], config.get("device", "cpu"), request.task)
    if request.model_id == "phikon":
        from PIL import Image
        with Image.open(files[0]) as image:
            if image.width * image.height > 10_000_000:
                raise ValueError("Use an image patch smaller than 10 megapixels.")
            inputs = processor(images=image.convert("RGB"), return_tensors="pt")
            quality = image_metrics(image)
    else:
        text = request.sequence if request.model_id == "esm2" else request.text
        inputs = processor(text, return_tensors="pt", truncation=True, max_length=1024)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.inference_mode():
        if request.task == "question_answering":
            output = model.generate(**inputs, max_new_tokens=max(1, min(int(request.options.get("max_new_tokens", 256)), 1024)), do_sample=False)
            content = processor.decode(output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
            return {"text": content}
        output = model(**inputs).last_hidden_state
        if request.model_id == "phikon":
            vector = output[:, 0, :]
        else:
            mask = inputs["attention_mask"].unsqueeze(-1)
            vector = (output * mask).sum(1) / mask.sum(1).clamp(min=1)
        result = {"embedding": vector[0].float().cpu().tolist(), "dimensions": vector.shape[-1], "kind": "representation", "note": "Embedding only; no validated diagnosis or task-specific prediction head."}
    if quality:
        result["image_quality"] = quality
        from pathlib import Path
        clip_weights = Path(config["weights"]).parent / "biomedclip-radiology"
        if (clip_weights / "open_clip_pytorch_model.bin").exists():
            from backend.adapters.biomedclip import infer as compare
            assessment = compare(request, files, {**config, "weights": str(clip_weights)})
            result.update({key: assessment[key] for key in ["candidate_scores", "candidate_basis"]})
            result["additional_model"] = "BiomedCLIP exploratory pattern comparison"
    else:
        result["text_measurements"] = text_metrics(request.text)
    return result
