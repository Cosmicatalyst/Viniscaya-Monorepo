def infer(request, files, config):
    import gc
    import torch
    import psutil
    from transformers import AutoTokenizer, EsmForProteinFolding
    if len(request.sequence) > 256:
        raise ValueError("Local folding limit is 256 residues.")
    if config.get("device", "cpu") == "cpu" and psutil.virtual_memory().available < 18 * 1024 ** 3:
        raise ValueError("Insufficient available RAM for CPU folding.")
    tokenizer = AutoTokenizer.from_pretrained(config["weights"], local_files_only=True)
    model = EsmForProteinFolding.from_pretrained(config["weights"], local_files_only=True, low_cpu_mem_usage=True).eval()
    model.trunk.set_chunk_size(32)
    model = model.to(config.get("device", "cpu"))
    tokens = tokenizer(request.sequence, return_tensors="pt", add_special_tokens=False)["input_ids"].to(next(model.parameters()).device)
    try:
        with torch.inference_mode():
            output = model(tokens, num_recycles=1)
        return {"pdb": model.output_to_pdb(output)[0], "residues": len(request.sequence), "mean_plddt": output["plddt"].float().mean().item(), "kind": "predicted_structure"}
    finally:
        del model
        gc.collect()
