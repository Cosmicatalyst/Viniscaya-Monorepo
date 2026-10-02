import json
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(ROOT / "weights" / ".hf")
os.environ["HF_HUB_DISABLE_XET"] = "1"
from huggingface_hub import snapshot_download

SOURCES = {
    "phikon": ("owkin/phikon", "057cc0295895c2df3dd7681a89680da6015cbefe", ["config.json", "model.safetensors", "preprocessor_config.json"], "backend.adapters.hf:infer"),
    "esmfold": ("facebook/esmfold_v1", "75a3841ee059df2bf4d56688166c8fb459ddd97a", ["config.json", "pytorch_model.bin", "special_tokens_map.json", "tokenizer_config.json", "vocab.txt"], "backend.adapters.esmfold:infer"),
    "pubmedbert": ("microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext", "e1354b7a3a09615f6aba48dfad4b7a613eef7062", ["config.json", "pytorch_model.bin", "tokenizer_config.json", "vocab.txt"], "backend.adapters.hf:infer"),
    "biomedclip-radiology": ("microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224", "9f341de24bfb00180f1b847274256e9b65a3a32e", ["open_clip_config.json", "open_clip_pytorch_model.bin", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt"], "backend.adapters.biomedclip:infer"),
    "qwen-small": ("Qwen/Qwen2.5-0.5B-Instruct", "7ae557604adf67be50417f59c2c2f167def9a775", ["*.json", "*.safetensors", "*.txt", "*.model"], "backend.adapters.text:infer"),
}
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-proteins", action="store_true")
    args = parser.parse_args()
    config_path = ROOT / "models.local.json"
    config = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
    for id, (repo, revision, patterns, adapter) in SOURCES.items():
        if id == "esmfold" and not args.include_proteins:
            continue
        directory = ROOT / "weights" / id
        print(f"Downloading {id}", flush=True)
        try:
            snapshot_download(repo, revision=revision, allow_patterns=patterns, local_dir=directory, max_workers=2)
            config[id] = {"enabled": bool(adapter), "adapter": adapter, "weights": str(directory), "device": "cpu"}
            print(f"Downloaded {id}", flush=True)
        except Exception as error:
            print(f"Failed {id}: {type(error).__name__}", flush=True)
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    if config.get("biomedclip-radiology", {}).get("enabled"):
        config["biomedclip-neurology"] = dict(config["biomedclip-radiology"])
    import requests
    echo_dir = ROOT / "weights" / "echonext"
    echo_dir.mkdir(parents=True, exist_ok=True)
    echo_base = "https://raw.githubusercontent.com/PierreElias/IntroECG/15233e9392e9dc10c136a5624abf10199207bce9/7-EchoNext%20Minimodel/models/echonext_multilabel_minimodel/"
    try:
        for name in ["weights.pt", "waveform_normalization_params.json"]:
            destination = echo_dir / name
            if not destination.exists():
                response = requests.get(echo_base + name, timeout=60)
                response.raise_for_status()
                destination.write_bytes(response.content)
        config["echonext"] = {"enabled": True, "adapter": "backend.adapters.echonext:infer", "weights": str(echo_dir), "device": "cpu"}
        print("EchoNext checkpoint installed", flush=True)
    except requests.RequestException:
        print("EchoNext download failed; it remains unconfigured.", flush=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
