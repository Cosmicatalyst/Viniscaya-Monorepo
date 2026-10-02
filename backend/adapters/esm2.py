"""Local ESM-2 representations; no folding or contact prediction."""
from functools import lru_cache
from argparse import Namespace
import re

@lru_cache(maxsize=1)
def load(weights, device):
    import torch
    import esm
    with torch.serialization.safe_globals([Namespace]):
        checkpoint = torch.load(weights, map_location="cpu", weights_only=True)
    cfg = checkpoint["cfg"]["model"]
    if (cfg.encoder_layers, cfg.encoder_embed_dim, cfg.encoder_attention_heads) != (30, 640, 20):
        raise ValueError("Expected ESM-2 t30 150M checkpoint.")
    alphabet = esm.Alphabet.from_architecture("ESM-1b")
    model = esm.model.esm2.ESM2(30, 640, 20, alphabet, token_dropout=cfg.token_dropout)
    state = {re.sub(r"^(encoder\.sentence_encoder\.|encoder\.)", "", k): v for k, v in checkpoint["model"].items()}
    missing, unexpected = model.load_state_dict(state, strict=False)
    allowed = {"contact_head.regression.weight", "contact_head.regression.bias"}
    if unexpected or set(missing) - allowed:
        raise ValueError("Checkpoint tensors do not match ESM-2 t30 150M.")
    return model.to(device).eval(), alphabet

def infer(request, files, config):
    import torch
    sequence = re.sub(r"\s+", "", request.sequence or "").upper()
    if not sequence or len(sequence) > 1022 or not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYBXZOU]+", sequence):
        raise ValueError("Provide 1–1022 amino-acid residues without FASTA headers.")
    model, alphabet = load(config["weights"], config.get("device", "cpu"))
    _, _, tokens = alphabet.get_batch_converter()([("protein", sequence)])
    with torch.inference_mode():
        output = model(tokens.to(next(model.parameters()).device), repr_layers=[30], return_contacts=False)
        residues = output["representations"][30][0, 1:len(sequence)+1]
        vector = residues.mean(0).float().cpu()
    return {"kind": "protein_representation", "embedding": vector.tolist(), "dimensions": 640, "residues": len(sequence), "representation_layer": 30, "pooling": "mean over residues, excluding special tokens", "note": "ESM-2 sequence representation only. No predicted structure, clinical diagnosis, or validated function prediction."}
