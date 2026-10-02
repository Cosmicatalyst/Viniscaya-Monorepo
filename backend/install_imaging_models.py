"""Reproduce the specialty checkpoint setup from official pinned sources."""
import hashlib, json
from pathlib import Path
import httpx
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parent
SOURCES={
 "medsiglip-448":("google/medsiglip-448","9cea28a1a1195f665105faa6e8544c112fd960a4",["*.json","*.safetensors","*.model","*.txt"]),
 "brats-mri":("MONAI/brats_mri_segmentation","370f7f9d062745fbac445e7fe6d6616d35df04ec",["models/model.pt","configs/inference.json","configs/metadata.json","docs/README.md","LICENSE"]),
}
if __name__=='__main__':
 for folder,(repo,revision,patterns) in SOURCES.items():
  snapshot_download(repo,revision=revision,allow_patterns=patterns,local_dir=ROOT/'weights'/folder,max_workers=2)
 target=ROOT/'weights'/'xrv-chest';target.mkdir(exist_ok=True)
 checkpoint=target/'model.pt'
 if not checkpoint.exists():
  url='https://github.com/mlmed/torchxrayvision/releases/download/v1/nih-pc-chex-mimic_ch-google-openi-kaggle-densenet121-d121-tw-lr001-rot45-tr15-sc15-seed0-best.pt'
  with httpx.stream('GET',url,follow_redirects=True,timeout=90) as response:
   response.raise_for_status()
   with checkpoint.open('wb') as f:
    for chunk in response.iter_bytes():f.write(chunk)
 if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!='56524913dd16a906422e8d8b66a7a5c46be1d82eb7ac012d8103776f1aa68899':raise ValueError('Official chest checkpoint hash mismatch.')
 if not (target/'state.pt').exists():
  import torch,torchxrayvision
  # The verified official legacy release stores a whole module. Convert once;
  # ongoing inference loads only tensors with weights_only=True.
  model=torch.load(checkpoint,map_location='cpu',weights_only=False)
  torch.save(model.state_dict(),target/'state.pt')
 config_path=ROOT/'models.local.json';config=json.loads(config_path.read_text(encoding='utf-8-sig')) if config_path.exists() else {}
 for id in ['medsiglip-radiology','medsiglip-neurology','xrv-chest','brats-mri']:
  folder='medsiglip-448' if id.startswith('medsiglip') else id
  adapter='medsiglip' if id.startswith('medsiglip') else 'xrv' if id=='xrv-chest' else 'brats'
  config[id]={'enabled':True,'weights':str(ROOT/'weights'/folder),'adapter':f'backend.adapters.{adapter}:infer','device':'cpu'}
 config_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
 print('Imaging specialist checkpoints configured.')
