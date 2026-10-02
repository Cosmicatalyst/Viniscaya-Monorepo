# Viniścaya local platform

Run the UI and Python API together from the repository root:

```powershell
npm run platform
```

UI: http://127.0.0.1:3000. REST documentation: http://127.0.0.1:8000/docs.
For separate terminals use `npm run dev` and `npm run api`. Do not run both startup methods at once. Ports 3000 and 8000 must be free for the combined command.

## Installed lightweight models

- Cancer: Phikon, pathology patch embeddings (768 dimensions).
- Radiology: BiomedCLIP, single-image embeddings and optional image/text similarity.
- Neurology: reuse BiomedCLIP for 2D brain-image representations. This is not an EEG runner or a brain-diagnosis model.
- Cardiac: official EchoNext minimodel, 12 research scores from preprocessed ECG and tabular arrays.
- General / Co-Doc: Qwen2.5-0.5B-Instruct, local drafting and streaming chat. PubMedBERT is also available through REST for text embeddings.
- Proteins: existing PDB/mmCIF viewer is available. ESMFold weights are downloaded but prediction is deferred and disabled.

The small general model is not a medically validated reasoning model. Image embeddings are not diagnoses. EchoNext scores require the official preprocessing and validation against the intended population. MedGemma is excluded.

## REST API

`GET /health` is public. All `/v1` routes require `Authorization: Bearer <MEDICAL_API_TOKEN>`. The ignored root `.env.local` supplies this token to the Python service and Next.js server. Browser requests use signed login sessions; the token stays on the server.

- `GET /v1/models?category=Cancer`: catalog, tasks, configuration status.
- `POST /v1/files`: multipart upload under `file`; returns an upload ID.
- `POST /v1/inference`: submit `model_id`, `task`, text or `file_ids`; returns a queued job.
- `GET /v1/jobs`: analysis history.
- `GET /v1/jobs/{id}`: job status and result.
- `GET /v1/jobs/{id}/result`: JSON download.
- `GET /v1/jobs/{id}/report`: evidence-bounded structured report; `?download=true` exports Markdown.
- `GET /v1/stats`: actual dashboard counts and the last seven UTC days of activity.
- `POST /v1/chat/completions`: OpenAI-style messages with model `qwen-small`; supports SSE `stream: true` and regular JSON responses.
- `GET /v1/threads`: saved conversations.
- `GET`, `PUT`, `DELETE /v1/threads/{id}`: retrieve, save, remove a conversation. ID is a 32-character lowercase hex string.

Co-Doc uses the local Python chat endpoint, renders Markdown, supports stopping a response, and saves conversations. Threads can reopen or delete saved chats. Library automatically lists completed analyses with result previews and downloads. Home graphs reflect stored records, not sample data.

## Inputs

Image runners accept one PNG/JPEG/TIFF under 100 MB and 10 megapixels. Cancer input is a pathology patch; whole-slide images need a separate patch/aggregation pipeline.

EchoNext accepts one NPZ, created from the upstream preprocessing output. `waveforms` must have shape `(1,1,2500,12)` and `tabular` shape `(1,7)`. Inputs must contain finite values and use the official normalization, lead ordering, and seven-feature ordering. Raw ECG images, arbitrary CSVs, and unnormalized arrays are not supported. See `vendor/ECHONEXT.md` and the official repository. Example packaging after preprocessing:

```python
import numpy as np
np.savez("ecg.npz", waveforms=np.load("waveforms.npy")[0:1], tabular=np.load("tabular_features.npy")[0:1])
```

The single-worker queue serializes model runs. Conversations, uploads, jobs, and results persist in ignored `backend/data`. This is a single-user local application; there is no per-user data isolation, automatic retention cleanup, or database encryption.

## Reinstall and configure

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt -r backend/requirements-models.txt
backend/.venv/Scripts/python.exe -m backend.download_weights
```

The downloader uses pinned Hugging Face revisions and skips protein weights by default. It downloads Phikon, PubMedBERT, BiomedCLIP, and Qwen; Neurology reuses BiomedCLIP. EchoNext's official minimodel weights are installed under `weights/echonext`. Trusted model paths/adapters are configured in ignored `models.local.json`; `models.example.json` shows the schema. Configuration is read on each request; restart after editing Python runner code. Inference uses local-only Transformers loading without remote checkpoint code.

## Verification

```powershell
npm run lint
npx tsc --noEmit
backend/.venv/Scripts/python.exe -m pytest backend/tests -q --basetemp=backend/data/test-temp
```

Tests cover authentication, validation, job execution, downloads, conversation persistence, statistics, and cardiac shape/finite-value validation. Separate smoke checks run real checkpoints with explicitly synthetic inputs; they verify integration, not clinical performance.

References: [Qwen](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct), [BiomedCLIP](https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224), [EchoNext minimodel](https://github.com/PierreElias/IntroECG/tree/master/7-EchoNext%20Minimodel).

Reports open in the right-side shadcn Sheet after a result completes or a saved result is opened. They contain the full measured inventory, provenance, quality limitations, missing context, model documentation, and reviewer sign-off. Composition is deterministic from stored outputs; it does not invent medical interpretations using the small text model. New results record original filenames and input context. Earlier analyses identify provenance as unrecorded. Reports are unsigned research drafts, not clinically validated findings.

Quantified reports now include source-image dimensions, 256x256 grayscale intensity summaries, entropy, gradient energy, and limited technical quality flags. Phikon pathology embeddings are accompanied by an auxiliary local BiomedCLIP comparison. Cancer, Radiology, and Neurology show fixed exploratory prompt banks with raw cosine scores; these are unconfirmed visual hypotheses, not diagnostic probabilities or complete differentials. All prompt strings are returned for review. General reports extract explicitly formatted BP, pulse, RR, SpO2, temperature, glucose, hemoglobin, and creatinine values from source text, preserving supplied units and marking missing units. No diagnosis, severity, or treatment is derived automatically. Rerun an analysis to obtain new image metrics and candidate scores for older saved results.


## Groq case reports

Set `GROQ_API_KEY` in the ignored root `.env.local`, then restart `npm run platform`.
The report service uses Groq `qwen/qwen3.8-27b` with reasoning disabled and hidden.
Credentials stay in Python; selected image previews and extracted case evidence are sent to Groq.
`POST /v1/cases` takes category, file_ids (up to 8) and optional text. No question is required.
Limits: 100 MB per file, 200 MB per case. Images: first frame, max 40 MP, preview max 1536px.
PDF: first 6 pages; extracted text capped at 12000 characters per file. DOCX: main text only.
DICOM: one selected instance / representative frame, with display windowing; no full-series interpretation.
NIfTI: up to 20 million voxels, nine spaced slices plus two orthogonal central slices, first timepoint. These are representative previews,
not a complete scan assessment. Missing, unsupported and failed sources remain visible in the report.
Prepared cardiac NPZ is routed to EchoNext. Other cardiac images contribute through Qwen vision only.
Radiology handles visible body regions without treating the previous chest candidate list as universal.
Each Groq vision call receives at most 3 labeled previews; all batches feed final synthesis.
The visible report contains medical findings and clinical values. Technical evidence stays in downloadable result JSON.
GET /v1/jobs/{id}/report returns generation_status; POST retries generation. Local processing survives
provider errors, which are shown explicitly. Reports are unsigned, unvalidated drafts requiring clinician review.
Protein sequence prediction remains deferred; existing structures can still be viewed.


## Imaging specialists
Radiology and Neurology now use Google's `google/medsiglip-448` (revision
`9cea28a1a1195f665105faa6e8544c112fd960a4`) for medical image/text embeddings and unconfirmed
prompt-alignment candidates. This is an encoder, not a report generator or validated diagnostic head.
Radiology additionally uses TorchXRayVision DenseNet121-all only when the encoder proposes a frontal
chest X-ray and the vision routing check confirms that view. Its 18 raw sigmoid scores remain research
outputs; there are no locally validated disease cutoffs. Other body regions continue to receive visual review.
Neurology can additionally run MONAI `brats_mri_segmentation` SegResNet (revision
`370f7f9d062745fbac445e7fe6d6616d35df04ec`). Upload one prepared study with four files named
`subject_t1ce.nii.gz`, `subject_t1.nii.gz`, `subject_t2.nii.gz`, `subject_flair.nii.gz`.
They must be co-registered, skull-stripped, 1 mm isotropic, and on an identical 3D voxel grid.
The pipeline verifies geometry/spacing and finite input but cannot certify skull stripping or acquisition.
It produces research tumor-core/whole-tumor/enhancing-tumor candidate masks and derived volumes,
not a general neurological disease detector. Missing sequences cause an explicit abstention.
CPU inference uses 128x128x96 sliding windows rather than the reference bundle's larger windows;
this implementation has not undergone clinical accuracy validation. The mask can be downloaded through
`GET /v1/jobs/{id}/segmentation`. Existing analyses retain their original outputs; rerun uploads to use new encoders.
Model metadata and raw evidence remain available in JSON; the report UI uses the Sushruta-1 display name.
