"""Compact local drafting/chat model. No remote code or network loading."""
from functools import lru_cache

SYSTEM = "You are Co-Doc, a concise assistant for clinicians. Help with drafting and research. State uncertainty, do not invent sources or patient details. Answer directly in Markdown without thinking blocks."

@lru_cache(maxsize=1)
def load(weights, device="cpu"):
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    torch.set_num_threads(4)
    tokenizer = AutoTokenizer.from_pretrained(weights, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(weights, local_files_only=True, torch_dtype=torch.float32, low_cpu_mem_usage=True).to(device).eval()
    return tokenizer, model

def inputs_for(tokenizer, model, messages):
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    if inputs["input_ids"].shape[-1] > 3072:
        raise ValueError("Conversation is too long for the local model. Start a new thread.")
    return inputs

def infer(request, files, config):
    import torch
    tokenizer, model = load(config["weights"], config.get("device", "cpu"))
    inputs = inputs_for(tokenizer, model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": request.text}])
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=384, do_sample=False, pad_token_id=tokenizer.eos_token_id)
    from backend.adapters.measurements import text_metrics
    return {"text": tokenizer.decode(output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True), "kind": "draft", "text_measurements": text_metrics(request.text)}
