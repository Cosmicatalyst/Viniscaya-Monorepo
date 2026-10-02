"""TorchXRayVision chest-only, raw sigmoid research scores."""
from pathlib import Path
from functools import lru_cache
import torch
import numpy as np
from PIL import Image
@lru_cache(maxsize=1)
def load(weights):
 import torchxrayvision as xrv
 model=xrv.models.DenseNet(weights=None,apply_sigmoid=True)
 model.load_state_dict(torch.load(Path(weights)/'state.pt',map_location='cpu',weights_only=True),strict=True)
 model.eval();return model,xrv.models.model_urls['all']['labels']
def infer(request,files,config):
 if request.options.get('confirmed_route')!='chest_xray_frontal': raise ValueError('Chest classifier requires a confidently routed frontal chest X-ray; other regions and views are not supported.')
 import torchxrayvision as xrv
 with Image.open(files[0]) as image: array=np.asarray(image.convert('L'),dtype=np.float32)
 array=xrv.datasets.normalize(array,255)[None]
 array=xrv.datasets.XRayCenterCrop()(array);array=xrv.datasets.XRayResizer(224)(array)
 model,labels=load(config['weights'])
 with torch.inference_mode(): values=model(torch.from_numpy(array)[None])[0].tolist()
 return {'model':'TorchXRayVision DenseNet121-all','kind':'classification','predictions':[{'label':label,'score':float(value)} for label,value in zip(labels,values)],'note':'Chest-only research sigmoid scores; no locally validated positive/negative cutoffs, no calibrated patient disease probability. Findings need image confirmation.'}
