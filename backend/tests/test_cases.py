import io, json, time
import httpx
from PIL import Image
from backend import main, groq_reports, cases
from backend.tests.test_api import client, wait

def test_multifile_case_coverage(client, monkeypatch):
 monkeypatch.delenv('GROQ_API_KEY',raising=False)
 uploads=[]
 for name,data in [('clinical.txt',b'BP 140/90 mmHg; HR 88 bpm.'),('invalid.png',b'not an image')]:
  uploads.append(client.post('/v1/files',files={'file':(name,data)}).json()['id'])
 response=client.post('/v1/cases',json={'category':'General','file_ids':uploads})
 assert response.status_code==202
 job=wait(client,response.json()['id']);assert job['status']=='completed'
 sources=job['result']['output']['sources']
 assert len(sources)==2 and sources[0]['status']=='processed' and sources[1]['status']=='unprocessed'
 assert '140/90' in job['result']['case_report']['markdown']
 report=client.get('/v1/jobs/'+job['id']+'/report').json()
 assert report['generation_status']=='configuration_required'
 assert client.post('/v1/cases',json={'category':'General','file_ids':[uploads[0],uploads[0]]}).status_code==422
 assert client.post('/v1/cases',json={'category':'Radiology'}).status_code==422
 assert client.post('/v1/cases',json={'category':'General','file_ids':['missing']}).status_code==404

def test_pdf_coverage(tmp_path):
 import pymupdf
 p=tmp_path/'sample.pdf';doc=pymupdf.open()
 for i in range(7): doc.new_page().insert_text((40,40),f'Synthetic page {i+1}')
 doc.save(p);doc.close()
 images,text,notes=cases.extract(p,p.name,tmp_path,'S1')
 assert len(images)==6 and 'page 7' not in text and '6 of 7' in notes[0]

def test_groq_batches_and_preserves_evidence(client,tmp_path,monkeypatch):
 images=[]
 for index in range(4):
  p=tmp_path/f'{index}.png';Image.new('RGB',(10,10)).save(p);images.append((f'S{index+1}',str(p)))
 payloads=[]
 def handle(request):
  payload=json.loads(request.content);payloads.append(payload)
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'Unsigned synthetic report'}}]})
 original_client=httpx.Client
 monkeypatch.setattr(groq_reports.httpx,'Client',lambda **kwargs: original_client(transport=httpx.MockTransport(handle),**kwargs))
 monkeypatch.setenv('GROQ_API_KEY','test-only')
 original={'title':'Test','scope':'research','markdown':'MEASURED SCORE 0.123456'}
 groq_reports.generate('a'*32,original,images)
 assert len(payloads)==3
 assert [sum(x.get('type')=='image_url' for x in p['messages'][1]['content']) for p in payloads[:2]]==[3,1]
 assert all(p['reasoning_effort']=='none' and p['reasoning_format']=='hidden' for p in payloads)
 saved=groq_reports.read('a'*32)
 assert saved['generation_status']=='completed' and saved['markdown']=='Unsigned synthetic report'
 assert '0.123456' in payloads[-1]['messages'][1]['content']
 assert saved['vision_markdown']
 assert 'S4' in payloads[-1]['messages'][1]['content']

def test_provider_failure_keeps_evidence(client,monkeypatch):
 original_client=httpx.Client
 monkeypatch.setattr(groq_reports.httpx,'Client',lambda **kwargs: original_client(transport=httpx.MockTransport(lambda request: httpx.Response(401,json={})),**kwargs))
 monkeypatch.setenv('GROQ_API_KEY','test-only')
 groq_reports.generate('b'*32,{'markdown':'Measured evidence'},[])
 saved=groq_reports.read('b'*32)
 assert saved['generation_status']=='failed' and saved['markdown']=='Measured evidence' and '401' in saved['generation_error']


def test_nifti_samples_and_coverage(tmp_path):
 import nibabel as nib
 import numpy as np
 p=tmp_path/'synthetic.nii.gz'
 nib.save(nib.Nifti1Image(np.zeros((8,8,12),dtype=np.float32),np.eye(4)),p)
 images,text,notes=cases.extract(p,p.name,tmp_path,'S1')
 assert len(images)==11 and '9 evenly spaced' in notes[0]
 assert 'not confirmed anatomical orientation' in notes[0]
