"""Google MedSigLIP-448 medical image/text alignment, not a diagnostic head."""
from functools import lru_cache
from PIL import Image
import torch

ROUTING = [
 ("chest_xray_frontal", "A frontal chest X-ray showing lungs, ribs and heart."),
 ("chest_xray_lateral", "A lateral chest X-ray."),
 ("bone_xray", "An X-ray of bones and joints outside the chest."),
 ("brain_mri", "A magnetic resonance image of the brain."),
 ("brain_ct", "A computed tomography image of the brain."),
 ("other_mri", "A magnetic resonance image of a non-brain body region."),
 ("other_ct", "A computed tomography image of a non-brain body region."),
 ("ultrasound", "A medical ultrasound scan."),
 ("pathology", "A microscopic histopathology tissue image."),
 ("document", "A page of a written clinical report or chart."),
 ("other", "A non-medical photograph or unclear image."),
]
NEURO = [
 ("Focal mass-like pattern", "Brain MRI with a focal mass-like lesion."),
 ("Mass effect pattern", "Brain image with midline displacement and mass effect."),
 ("Ventricular enlargement pattern", "Brain image with enlarged ventricles."),
 ("White matter signal pattern", "Brain MRI with white matter signal abnormalities."),
 ("Hemorrhage-like pattern", "Brain CT with a focal hyperdense hemorrhage-like region."),
 ("No conspicuous focal change", "Brain image without a conspicuous focal abnormality."),
]
BONE = [("Cortical disruption pattern", "Bone X-ray with a fracture and cortical discontinuity."),("Joint degeneration pattern", "Joint X-ray with joint space narrowing and osteophytes."),("Displacement pattern", "Joint X-ray with dislocation or misalignment."),("No conspicuous focal change", "Bone X-ray without a conspicuous focal abnormality.")]
@lru_cache(maxsize=1)
def load(weights):
 from transformers import AutoModel, AutoProcessor
 model=AutoModel.from_pretrained(weights,local_files_only=True,torch_dtype=torch.float32,trust_remote_code=False).eval()
 processor=AutoProcessor.from_pretrained(weights,local_files_only=True,trust_remote_code=False,use_fast=False)
 return processor,model

def infer(request,files,config):
 if len(files)!=1: raise ValueError("MedSigLIP takes one 2D preview per invocation.")
 processor,model=load(config['weights'])
 with Image.open(files[0]) as source:
  if source.width*source.height>10_000_000: raise ValueError("Use a preview under 10 megapixels.")
  image=source.convert('RGB')
 inputs=processor(images=image,text=[text for _,text in ROUTING],padding='max_length',truncation=True,max_length=64,return_tensors='pt')
 with torch.inference_mode():
  outputs=model(**inputs);image_vector=torch.nn.functional.normalize(outputs.image_embeds,dim=-1)
  text_vectors=torch.nn.functional.normalize(outputs.text_embeds,dim=-1)
  similarities=(image_vector@text_vectors.T)[0].tolist()
 ranked=sorted([{'label':label,'score':score} for (label,_),score in zip(ROUTING,similarities)],key=lambda x:x['score'],reverse=True)
 margin=ranked[0]['score']-ranked[1]['score']
 # Abstention rule is a conservative engineering heuristic, not a validated modality classifier.
 route=ranked[0]['label'] if margin>=.035 and ranked[0]['score']>=.15 else 'uncertain'
 result={'model':'Google MedSigLIP-448','kind':'representation','dimensions':len(image_vector[0]),'embedding':image_vector[0].tolist(),'routing':{'selected':route,'margin':margin,'candidates':ranked,'basis':'Unvalidated prompt-alignment routing; uncertain inputs never enter a chest-only classifier.'}}
 candidates=NEURO if route in {'brain_mri','brain_ct'} else BONE if route=='bone_xray' else []
 if candidates:
  tokens=processor(text=[text for _,text in candidates],padding='max_length',truncation=True,max_length=64,return_tensors='pt')
  with torch.inference_mode():
   vectors=torch.nn.functional.normalize(model.get_text_features(**tokens),dim=-1);scores=(image_vector@vectors.T)[0].tolist()
  result['candidate_scores']=sorted([{'label':label,'score':score,'prompt':prompt} for (label,prompt),score in zip(candidates,scores)],key=lambda x:x['score'],reverse=True)
  result['candidate_basis']='Unconfirmed zero-shot cosine alignment, not a finding or disease probability. Use only as hypotheses to check against primary images.'
 return result
