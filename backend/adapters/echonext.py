"""Official EchoNext minimodel; accepts the published preprocessed arrays only."""
from pathlib import Path
import zipfile

LABELS = ["LVEF ≤45%", "LV wall thickness ≥13 mm", "Aortic stenosis", "Aortic regurgitation", "Mitral regurgitation", "Tricuspid regurgitation", "Pulmonary regurgitation", "RV systolic dysfunction", "Pericardial effusion", "PASP ≥45 mmHg", "TR velocity ≥3.2 m/s", "Structural heart disease"]

def read_input(path):
    import numpy as np
    if path.suffix != ".npz":
        raise ValueError("Upload an NPZ with preprocessed waveforms and tabular arrays.")
    with zipfile.ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > 32 * 1024 * 1024:
            raise ValueError("Uncompressed input is too large.")
    with np.load(path, allow_pickle=False) as data:
        if not {"waveforms", "tabular"}.issubset(data.files):
            raise ValueError("NPZ needs waveforms and tabular keys.")
        waveforms = np.asarray(data["waveforms"], dtype=np.float32)
        tabular = np.asarray(data["tabular"], dtype=np.float32)
    if waveforms.shape == (1, 2500, 12): waveforms = waveforms[None]
    if tabular.shape == (7,): tabular = tabular[None]
    if waveforms.shape != (1, 1, 2500, 12) or tabular.shape != (1, 7):
        raise ValueError("Expected one ECG: waveforms (1,1,2500,12), tabular (1,7).")
    if not np.isfinite(waveforms).all() or not np.isfinite(tabular).all():
        raise ValueError("Arrays must contain finite values.")
    return waveforms, tabular

def infer(request, files, config):
    import torch
    from backend.vendor.echonext_resnet import ResNet1dWithTabular
    waveforms, tabular = read_input(files[0])
    model = ResNet1dWithTabular(len_tabular_feature_vector=7, filter_size=16, num_classes=12).eval()
    checkpoint = torch.load(Path(config["weights"]) / "weights.pt", map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model"])
    with torch.inference_mode():
        values = torch.sigmoid(model((torch.from_numpy(waveforms), torch.from_numpy(tabular))))[0].tolist()
    return {"predictions": [{"label": label, "score": score} for label, score in zip(LABELS, values)], "kind": "research_scores", "note": "Requires official EchoNext preprocessing; scores are research outputs, not diagnoses."}
