"""Official MONAI BraTS SegResNet; four co-registered preprocessed MRI volumes."""
import re
from pathlib import Path
import numpy as np

ORDER = ["t1ce", "t1", "t2", "flair"]
def select(rows):
    selected = {}
    for row in rows:
        name = row["name"].lower()
        if not name.endswith((".nii", ".nii.gz")): continue
        stem = name.removesuffix(".gz").removesuffix(".nii")
        match = re.search(r"(?:^|[_\- .])(t1ce|t1c|t1gd|t1|t2|flair)(?:$|[_\- .])", stem)
        if not match: continue
        sequence = "t1ce" if match[1] in {"t1ce", "t1c", "t1gd"} else match[1]
        if sequence in selected: raise ValueError("Multiple MRI volumes for one sequence; submit one co-registered study per case.")
        selected[sequence] = row["path"]
    missing = [name for name in ORDER if name not in selected]
    if missing: raise ValueError("3D tumor analysis needs named T1ce, T1, T2 and FLAIR NIfTI volumes. Missing: " + ", ".join(missing))
    return [Path(selected[name]) for name in ORDER]

def load_inputs(files):
    import nibabel as nib
    volumes = [nib.load(path) for path in files]
    first = volumes[0]
    if len(first.shape) != 3 or np.prod(first.shape) > 16_000_000: raise ValueError("Use 3D MRI volumes up to 16 million voxels.")
    for volume in volumes:
        if volume.shape != first.shape or not np.allclose(volume.affine, first.affine, atol=1e-3): raise ValueError("MRI sequences must share a co-registered voxel grid and affine.")
        if not np.allclose(volume.header.get_zooms()[:3], (1,1,1), atol=.05): raise ValueError("BraTS expects preprocessed, co-registered 1 mm isotropic MRI volumes.")
    arrays = []
    for volume in volumes:
        array = volume.get_fdata(dtype=np.float32)
        if not np.isfinite(array).all(): raise ValueError("MRI contains nonfinite values.")
        mask = array != 0
        if not mask.any(): raise ValueError("MRI sequence has no nonzero signal.")
        sd = array[mask].std()
        if sd < 1e-6: raise ValueError("MRI sequence lacks usable intensity variation.")
        array[mask] = (array[mask] - array[mask].mean()) / sd
        arrays.append(array)
    return np.stack(arrays), first

def infer(request, files, config):
    import torch, psutil, nibabel as nib
    from monai.networks.nets import SegResNet
    from monai.inferers import sliding_window_inference
    if len(files) != 4: raise ValueError("Four MRI sequences are required in T1ce, T1, T2, FLAIR order.")
    if psutil.virtual_memory().available < 4 * 1024**3: raise ValueError("At least 4 GB free RAM is required for volumetric MRI analysis.")
    array, reference = load_inputs(files)
    model = SegResNet(blocks_down=[1,2,2,4], blocks_up=[1,1,1], init_filters=16, in_channels=4, out_channels=3, dropout_prob=.2)
    state = torch.load(Path(config["weights"])/"models/model.pt", map_location="cpu", weights_only=True)
    model.load_state_dict(state.get("model",state), strict=True);model.eval()
    with torch.inference_mode():
        logits = sliding_window_inference(torch.from_numpy(array)[None], (128,128,96), 1, model, overlap=.5)
        masks = (logits.sigmoid()[0].numpy() >= .5)
    folder = Path(request.options["artifact_dir"])
    folder.mkdir(parents=True,exist_ok=True)
    labels = np.where(masks[2],4,np.where(masks[0],1,np.where(masks[1],2,0))).astype(np.uint8)
    target = folder/"brain-tumor-segmentation.nii.gz"
    nib.save(nib.Nifti1Image(labels,reference.affine),target)
    voxel_ml = abs(float(np.linalg.det(reference.affine[:3,:3]))) / 1000
    regions = [{"label":label,"voxel_count":int(mask.sum()),"predicted_volume_ml":round(float(mask.sum())*voxel_ml,3)} for label,mask in zip(["Tumor core candidate","Whole tumor candidate","Enhancing tumor candidate"],masks)]
    return {"model":"MONAI BraTS SegResNet","kind":"segmentation","regions":regions,"mask_file":str(target),"note":"Research-predicted regions, not confirmed tumor or histology. Requires BraTS-like skull-stripped/co-registered 1 mm T1ce/T1/T2/FLAIR. Smaller CPU windows than reference bundle; no local clinical validation. Does not detect every neurological disease."}
