"""Upload-first case processing with per-source coverage and bounded extraction."""
import importlib, json, zipfile
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
from uuid import uuid4
import numpy as np
from PIL import Image
from fastapi import HTTPException
from pydantic import BaseModel, Field
from backend import main
from backend.catalog import MODEL_MAP
from backend.workspace import router

class CaseRequest(BaseModel):
 category: str
 file_ids: list[str] = Field(default_factory=list,max_length=8)
 text: str = Field(default='',max_length=16000)

MAPPING={'Cancer':'phikon','Radiology':'medsiglip-radiology','Neurology':'medsiglip-neurology','Cardiac':'echonext','General':'qwen-small'}

def extract(path, name, folder, source_id):
 """All sampling and truncation recorded; unsupported inputs never imply negative findings."""
 images=[]; text=''; notes=[]
 suffix=''.join(path.suffixes).lower()
 def image_save(image,label):
  image.thumbnail((1536,1536));target=folder/f'{source_id}-{len(images)}.png';image.convert('RGB').save(target)
  images.append((f'{source_id}: {name} / {label}',str(target)))
 def array_save(array,label):
  a=np.asarray(array,dtype=np.float32)
  if not np.isfinite(a).all(): raise ValueError('Nonfinite image pixels.')
  lo,hi=np.percentile(a,[1,99]); a=np.clip((a-lo)/max(float(hi-lo),1e-8)*255,0,255).astype(np.uint8)
  image_save(Image.fromarray(a),label+' / percentile normalized display')
 if suffix in {'.png','.jpg','.jpeg','.tif','.tiff'}:
  with Image.open(path) as image:
   if image.width*image.height>40_000_000: raise ValueError('Image exceeds 40 megapixels.')
   frames=getattr(image,"n_frames",1)
   indices=sorted(set(np.linspace(0,frames-1,min(frames,6),dtype=int).tolist()))
   for index in indices:
    image.seek(index);image_save(image.copy(),f'frame {index+1}')
   notes.append(f'{len(indices)} of {frames} frames sampled; resized previews, not whole-slide assessment.')
 elif suffix=='.pdf':
  import pymupdf
  with pymupdf.open(path) as doc:
   if doc.needs_pass: raise ValueError('Encrypted PDF cannot be read.')
   for index in range(min(len(doc),6)):
    page=doc[index];text+=f'\nPage {index+1}: '+page.get_text()[:8000]
    scale=min(1,1536/max(page.rect.width,page.rect.height,1))
    pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
    image_save(Image.frombytes('RGB',[pix.width,pix.height],pix.samples),f'page {index+1}')
   notes.append(f'First {min(len(doc),6)} of {len(doc)} PDF pages extracted; max 8000 text characters per page.')
 elif suffix in {'.txt','.csv'}:
  text=path.read_bytes()[:60000].decode('utf-8-sig',errors='replace');notes.append('Text limited to first 60000 bytes.')
 elif suffix=='.docx':
  from defusedxml import ElementTree
  with zipfile.ZipFile(path) as z:
   entry=z.getinfo('word/document.xml')
   if entry.file_size>5_000_000: raise ValueError('DOCX text XML exceeds extraction limit.')
   root=ElementTree.fromstring(z.read(entry)); text=' '.join(root.itertext())[:60000]
  notes.append('Main document text only, first 60000 characters; embedded images not assessed.')
 elif suffix=='.dcm':
  import pydicom
  from pydicom.pixels import apply_modality_lut, apply_voi_lut
  ds=pydicom.dcmread(path)
  if int(getattr(ds,'Rows',0))*int(getattr(ds,'Columns',0))*int(getattr(ds,'NumberOfFrames',1))>20_000_000: raise ValueError('DICOM exceeds pixel limit.')
  a=apply_voi_lut(apply_modality_lut(ds.pixel_array,ds),ds)
  count=int(getattr(ds,'NumberOfFrames',1))
  indices=sorted(set(np.linspace(0,count-1,min(count,9),dtype=int).tolist()))
  for index in indices:
   frame=a[index] if count>1 else a
   if frame.ndim==3 and frame.shape[-1] in (3,4): image_save(Image.fromarray(frame.astype(np.uint8)),f'color frame {index+1}')
   else:
    if getattr(ds,'PhotometricInterpretation','')=='MONOCHROME1': frame=-frame.astype(np.float32)
    array_save(frame,f'frame {index+1}')
  text='DICOM acquisition metadata: '+json.dumps({k:str(getattr(ds,k,'')) for k in ['Modality','BodyPartExamined','StudyDescription','SeriesDescription','PixelSpacing','SliceThickness']})
  notes.append(f'{len(indices)} of {count} frames sampled; selected instance only, not a complete DICOM series.')
 elif suffix in {'.nii','.nii.gz'}:
  import nibabel as nib
  obj=nib.load(path)
  if len(obj.shape)<3 or len(obj.shape)>4 or np.prod(obj.shape)>20_000_000: raise ValueError('NIfTI must be 3D/4D with at most 20 million voxels.')
  a=np.asarray(obj.dataobj,dtype=np.float32)
  if a.ndim==4: a=a[:,:,:,0]
  indices=sorted(set(np.linspace(0,a.shape[2]-1,min(a.shape[2],9),dtype=int).tolist()))
  for index in indices: array_save(np.rot90(a[:,:,index]),f'voxel axis 2 slice {index+1}/{a.shape[2]}')
  for axis in (0,1): array_save(np.rot90(np.take(a,a.shape[axis]//2,axis=axis)),f'central slice voxel axis {axis}')
  text=f'NIfTI shape: {obj.shape}; voxel spacing: {obj.header.get_zooms()}'
  notes.append(f'{len(indices)} evenly spaced voxel-axis-2 slices plus two orthogonal central slices; first timepoint. Voxel axes are not confirmed anatomical orientation. No full-volume lesion detection or segmentation.')
 elif suffix=='.npz': notes.append('Prepared numeric arrays routed to EchoNext only; no visual interpretation.')
 else: raise ValueError('Format is not supported by the case report pipeline.')
 if len(text)>12000:
  text=text[:12000];notes.append("Extracted text truncated to 12000 characters for this source.")
 return images,text,notes

def run_case(id,body,rows,model_id):
 try:
  with main.db() as con: con.execute("UPDATE jobs SET status='running' WHERE id=?",(id,))
  folder=main.DATA/'results'/f'{id}-assets';folder.mkdir()
  evidence=[];assets=[];manifest=[]
  config=main.configurations().get(model_id,{})
  for index,row in enumerate(rows):
   source=f'S{index+1}';entry={'source':source,'name':row['name'],'status':'processed'}
   try:
    previews,text,notes=extract(Path(row['path']),row['name'],folder,source);assets+=previews
    entry['coverage']=notes;entry['text']=text
    outputs=[]
    targets=([Path(row['path'])] if body.category=='Cardiac' and row['path'].endswith('.npz') else [Path(p) for _,p in previews] if body.category in {'Cancer','Radiology','Neurology'} else [])
    for target in targets:
     try:
      status,reason=main.availability(MODEL_MAP[model_id],config)
      if status!='configured': raise ValueError(reason)
      module,function=config.get('adapter',MODEL_MAP[model_id].get('builtin_adapter')).split(':')
      request=SimpleNamespace(model_id=model_id,task=MODEL_MAP[model_id]['tasks'][0],text=None,sequence=None,options={})
      output=getattr(importlib.import_module(module),function)(request,[target],config)
      # Fixed disease prompt sets are unsuitable for arbitrary radiology: vision synthesis assesses visible region instead.
      if body.category=='Radiology' and output.get('routing',{}).get('candidates',[{}])[0].get('label')=='chest_xray_frontal':
       try:
        from backend.adapters.xrv import infer as chest_infer
        from backend.groq_reports import confirm_frontal_chest
        chest_config=main.configurations().get('xrv-chest',{})
        chest_status,_=main.availability(MODEL_MAP['xrv-chest'],chest_config)
        if chest_status=='configured' and confirm_frontal_chest(target):
         request.options={'confirmed_route':'chest_xray_frontal'}
         outputs.append(chest_infer(request,[target],chest_config))
        else: output['specialist_status']='Chest classifier skipped: frontal chest view not confirmed or model unavailable.'
       except Exception:
        output['specialist_status']='Chest classifier skipped: view confirmation or specialist inference unavailable.'
      outputs.append(output)
     except Exception as error: outputs.append({'unavailable':str(error)[:250] if isinstance(error,ValueError) else 'Local model could not process this source.'})
    entry['outputs']=outputs
    if not previews and not text and not outputs: entry['status']='unassessed'
    from backend.adapters.measurements import text_metrics
    entry['text_measurements']=text_metrics(text) if text else None
   except Exception as error:
    entry['status']='unprocessed';entry['error']=str(error)[:250] if isinstance(error,ValueError) else 'Source extraction failed; this source was not assessed.'
   manifest.append(entry)
  if body.category=='Neurology':
   from backend.adapters import brats,medsiglip
   specialist={'source':'N1','name':'3D MRI tumor-region analysis','status':'unassessed','outputs':[]}
   try:
    sequences=brats.select(rows)
    medsiglip.load.cache_clear()
    import gc
    gc.collect()
    brain_config=main.configurations().get('brats-mri',{})
    status,reason=main.availability(MODEL_MAP['brats-mri'],brain_config)
    if status!='configured': raise ValueError(reason)
    request=SimpleNamespace(options={'artifact_dir':str(folder)})
    specialist['outputs']=[brats.infer(request,sequences,brain_config)];specialist['status']='processed'
   except Exception as error:
    specialist['error']=str(error)[:250] if isinstance(error,ValueError) else '3D brain analysis could not complete; no segmentation finding is available.'
   manifest.append(specialist)
  # Exclude high-dimensional vectors from language prompts; preserve values and original JSON for download.
  def compact(value):
   if isinstance(value,dict): return {k:compact(v) for k,v in value.items() if k not in {'embedding','pdb'}}
   if isinstance(value,list): return [compact(v) for v in value]
   return value
  evidence_markdown='# Case evidence\n\nUnsigned research draft. Missing sources are not negative findings.\n\n'
  evidence_markdown+='Clinical context supplied:\n'+body.text+'\n\n'
  evidence_markdown+='Synthetic source flag: '+str(any('synthetic' in r['name'].lower() for r in rows))+'\n\n'
  for entry in manifest: evidence_markdown+='## '+entry['source']+'\n\n```json\n'+json.dumps(compact(entry),ensure_ascii=False,indent=2)+'\n```\n\n'
  result={'model_id':model_id,'task':'case_report','input':{'files':[r['name'] for r in rows],'file_ids':body.file_ids,'text':body.text,'synthetic_label':any('synthetic' in r['name'].lower() for r in rows)},'output':{'sources':manifest,'text':'Case evidence prepared. See the full report for findings, values and source coverage.'},'case_report':{'title':body.category+' case report','scope':'Selected-source review · Not clinically validated','markdown':evidence_markdown,'clinical_status':'unverified','job_id':id},'report_assets':assets}
  path=main.DATA/'results'/f'{id}.json';path.write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
  with main.db() as con: con.execute("UPDATE jobs SET status='completed',result_path=? WHERE id=?",(str(path),id))
  from backend.groq_reports import ensure
  ensure(id,result['case_report'],assets)
 except Exception:
  with main.db() as con: con.execute("UPDATE jobs SET status='failed',error='Case preparation failed.' WHERE id=?",(id,))
 finally: main.slots.release()

@router.post('/v1/cases',status_code=202)
def case(body:CaseRequest):
 model_id=MAPPING.get(body.category)
 if not model_id: raise HTTPException(422,'This category does not support case reports.')
 if not body.file_ids and not body.text.strip(): raise HTTPException(422,'Upload source files or provide clinical text.')
 if len(set(body.file_ids))!=len(body.file_ids): raise HTTPException(422,'Duplicate sources are not allowed.')
 with main.db() as con: rows=[con.execute('SELECT * FROM files WHERE id=?',(id,)).fetchone() for id in body.file_ids]
 if any(row is None for row in rows): raise HTTPException(404,'Source file not found.')
 if sum(row['size'] for row in rows)>200*1024*1024: raise HTTPException(413,'Case limit is 200 MB total.')
 if not main.slots.acquire(blocking=False): raise HTTPException(429,'Analysis queue full.')
 id=uuid4().hex
 try:
  with main.db() as con: con.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',(id,model_id,'case_report','queued',datetime.now(timezone.utc).isoformat(),None,None))
  main.pool.submit(run_case,id,body,[dict(row) for row in rows],model_id)
 except Exception: main.slots.release();raise
 return {'id':id,'status':'queued'}


SAMPLES = {
 'Cancer': {'default':'cancer-h-and-e.jpg','adenocarcinoma':'cancer-adenocarcinoma.jpg'},
 'Radiology': {'default':'radiology-chest-xray.jpg','bone':'radiology-bone-xray.jpg'},
 'Neurology': {'default':'neurology-brain-mri.jpg'},
 'Cardiac': {'default':'cardiac-SYNTHETIC-pipeline-test.npz'},
 'General': {'default':'general-fictional-note.txt'},
 'Proteins': {'default':'protein-crambin-1CRN.pdb'},
}
class SampleRequest(BaseModel):
 category: str
 variant: str = 'default'

@router.post('/v1/samples',status_code=202)
def sample(body: SampleRequest):
 import shutil
 filename=SAMPLES.get(body.category,{}).get(body.variant)
 if not filename: raise HTTPException(422,'Unknown sample.')
 path=main.ROOT.parent/'test-assets'/filename
 if not path.is_file(): raise HTTPException(503,'Bundled sample file is unavailable.')
 notice='Demo sample, not a patient case. Outputs are unverified research results.'
 if body.category=='Proteins': return {'kind':'structure','pdb':path.read_text(encoding='utf-8'),'name':'Crambin 1CRN','notice':'Public experimental structure for viewer testing; not a sequence prediction.'}
 if body.category=='Cardiac': notice='Synthetic ECG pipeline test only. Scores have no clinical meaning.'
 if body.category=='General': notice='Fictional clinical note for testing only.'
 id=uuid4().hex;target=main.DATA/'uploads'/(id+path.suffix)
 shutil.copyfile(path,target)
 with main.db() as con: con.execute('INSERT INTO files VALUES (?,?,?,?)',(id,'DEMO_'+filename,str(target),target.stat().st_size))
 created=case(CaseRequest(category=body.category,file_ids=[id],text=notice+' Do not infer a real patient diagnosis or treatment.'))
 return {**created,'sample_name':filename,'sample_notice':notice,'sample_file_ids':[id]}
