import json
from pathlib import Path
import numpy as np
import nibabel as nib
import pytest
from types import SimpleNamespace
from backend.adapters import brats, xrv
from backend.tests.test_api import client,wait

def test_mri_sequence_selection_and_validation(tmp_path):
 rows=[]
 for sequence in brats.ORDER:
  p=tmp_path/f"subject_{sequence}.nii.gz"
  nib.save(nib.Nifti1Image(np.random.default_rng(1).normal(size=(8,8,8)).astype(np.float32),np.eye(4)),p)
  rows.append({'name':p.name,'path':str(p)})
 assert brats.select(rows)==[Path(row['path']) for row in rows]
 array,reference=brats.load_inputs(brats.select(rows))
 assert array.shape==(4,8,8,8) and np.isfinite(array).all()
 with pytest.raises(ValueError,match='Missing'): brats.select(rows[:3])
 with pytest.raises(ValueError,match='Multiple'): brats.select(rows+[rows[0]])
 image=nib.load(rows[-1]['path']);affine=image.affine.copy();affine[0,3]=10
 nib.save(nib.Nifti1Image(image.get_fdata(),affine),rows[-1]['path'])
 with pytest.raises(ValueError,match='co-registered'): brats.load_inputs(brats.select(rows))

def test_chest_scope_gate():
 with pytest.raises(ValueError,match='frontal chest'):xrv.infer(SimpleNamespace(options={'confirmed_route':'bone_xray'}),[],{})

def test_catalog_upgrade_and_direct_mri_contract(client):
 models=client.get('/v1/models').json()['models']
 assert any(m['id']=='medsiglip-radiology' for m in models)
 assert any(m['id']=='brats-mri' for m in models)
 assert not any(m['id']=='biomedclip-neurology' for m in models)
 assert client.post('/v1/inference',json={'model_id':'brats-mri','task':'segmentation','file_ids':['a']}).status_code==422
 assert client.get('/v1/jobs/'+'c'*32+'/segmentation').status_code==404


def test_segmentation_download_stays_in_job_directory(client):
 from backend import main
 id='d'*32
 folder=main.DATA/'results'/f'{id}-assets';folder.mkdir()
 mask=folder/'brain-tumor-segmentation.nii.gz';mask.write_bytes(b'test-mask-only')
 result_path=main.DATA/'results'/f'{id}.json'
 def write_result(path):result_path.write_text(json.dumps({'output':{'sources':[{'outputs':[{'mask_file':str(path)}]}]}}),encoding='utf-8')
 write_result(mask)
 with main.db() as con:con.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',(id,'brats-mri','case_report','completed','2026-10-02',None,str(result_path)))
 response=client.get('/v1/jobs/'+id+'/segmentation')
 assert response.status_code==200 and response.content==b'test-mask-only'
 outside=main.DATA/'outside.nii.gz';outside.write_bytes(b'outside')
 write_result(outside)
 assert client.get('/v1/jobs/'+id+'/segmentation').status_code==404
 assert client.get('/v1/jobs/'+id+'/segmentation',headers={'Authorization':'Bearer wrong'}).status_code==401


def test_report_context_and_thread_attachments(client):
 from backend import main
 id='e'*32
 result=main.DATA/'results'/f'{id}.json'
 result.write_text(json.dumps({'output':{'predictions':[{'label':'Test candidate','score':0.1234}],'embedding':[1,2,3]}}),encoding='utf-8')
 with main.db() as con:con.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',(id,'xrv-chest','classification','completed','2026-10-02',None,str(result)))
 context=client.get('/v1/jobs/'+id+'/chat-context')
 assert context.status_code==200 and '0.1234' in context.json()['context'] and 'embedding' not in context.json()['context']
 thread='f'*32
 assert client.put('/v1/threads/'+thread,json={'messages':[{'role':'user','content':'Discuss this report'}],'report_ids':[id]}).status_code==200
 assert client.get('/v1/threads/'+thread).json()['report_ids']==[id]
 assert client.put('/v1/threads/'+thread,json={'messages':[{'role':'user','content':'Discuss'}],'report_ids':['missing']}).status_code==404


def test_bundled_samples(client,monkeypatch):
 from backend import cases
 monkeypatch.delenv('GROQ_API_KEY',raising=False)
 response=client.post('/v1/samples',json={'category':'General'})
 assert response.status_code==202 and 'Fictional' in response.json()['sample_notice']
 job=wait(client,response.json()['id']);assert job['status']=='completed'
 assert job['result']['input']['files'][0].startswith('DEMO_')
 assert 'fictional' in job['result']['input']['text'].lower()
 assert client.post('/v1/samples',json={'category':'Proteins'}).json()['pdb'].startswith('HEADER')
 assert client.post('/v1/samples',json={'category':'Radiology','variant':'../../bad'}).status_code==422
 assert client.post('/v1/samples',json={'category':'General'},headers={'Authorization':'Bearer wrong'}).status_code==401


def test_source_previews(client):
 import io
 from PIL import Image
 buffer=io.BytesIO();Image.new('RGB',(20,30),'white').save(buffer,format='PNG')
 upload=client.post('/v1/files',files={'file':('scan.png',buffer.getvalue())}).json()
 preview=client.get('/v1/files/'+upload['id']+'/preview')
 assert preview.status_code==200 and preview.json()['images'][0]['src'].startswith('data:image/png;base64,')
 note=client.post('/v1/files',files={'file':('note.txt',b'Fictional clinical note')}).json()
 assert client.get('/v1/files/'+note['id']+'/preview').json()['text']=='Fictional clinical note'
 assert client.get('/v1/files/'+note['id']+'/preview',headers={'Authorization':'Bearer wrong'}).status_code==401
 invalid=client.post('/v1/files',files={'file':('scan.png',b'invalid')}).json()
 assert client.get('/v1/files/'+invalid['id']+'/preview').status_code==422
 assert client.get('/v1/files/'+'a'*32+'/preview').status_code==404
