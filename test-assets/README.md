# Platform test pack

Open http://127.0.0.1:3000 and sign in. These files are in this directory. Upload one file at a time.

## Cancer

Use `cancer-h-and-e.jpg`, then `cancer-adenocarcinoma.jpg`. Select **Run analysis**. Expect a completed job, 768 embedding dimensions, and a small representation chart. Filenames describe the source examples; the installed runner does not classify cancer.

## Radiology

Use `radiology-chest-xray.jpg` or `radiology-bone-xray.jpg`. Optional comparison text: `A chest X-ray.` or `A bone X-ray.` Expect 512-dimensional image embeddings and a cosine-similarity value if text is supplied. Similarity is not a diagnosis or probability.

## Neurology

Use `neurology-brain-mri.jpg`. Optional comparison text: `A brain MRI image.` Expect 512-dimensional embeddings. This tests the 2D biomedical-image runner, not EEG processing or a full MRI-volume diagnosis.

## Cardiac

Use `cardiac-SYNTHETIC-pipeline-test.npz`. It contains generated pulse-like waveforms and zero-valued tabular features in the required shapes. Expect a completed job and 12 scores. This synthetic input verifies that upload, array loading, inference, and result rendering work. Its scores have no clinical meaning; it is not a real patient ECG or a validated normalized input.

Then use `cardiac-INVALID-shape.npz`. Expect a failed job with an input-shape error. This checks input validation.

## Proteins

In **Proteins**, choose **Load structure** and select `protein-crambin-1CRN.pdb`. Rotate, zoom, switch ribbon/stick/sphere modes, and reset the camera. This is an existing experimental structure, not a sequence prediction. `protein-sequence-DEFERRED.txt` is provided for future folding tests; prediction is currently disabled.

## General

Open `general-fictional-note.txt`, copy its contents into the General text box, and run analysis. Expect generated text, a completed job, and a downloadable JSON result. The scenario is fictional. The local model is small, so assess the text separately from whether the feature works.

## Co-Doc and Threads

Copy a prompt from `chat-prompts.txt` into Co-Doc. Check that text streams, Markdown renders, and follow-up questions work. Try the stop button during another response. A completed conversation should appear under **Threads**. Open it again and verify the messages are restored. Try **New conversation** for a fresh chat. Delete only test conversations you no longer need.

## Library and Home

After running an analysis, open **Library**, select the result, and download its JSON. **Home** should show the stored analysis counts and activity graphs. Jobs in this test pack are real runs on public or synthetic inputs; do not treat their scores as clinical validation.

## Error handling

Upload `image-INVALID-empty.jpg` to Cancer or Radiology. Expect an empty-file error. Upload the wrong-shaped cardiac file to check the adapter's validation. If the Python service is stopped, screens should report that the API is unavailable.

## Sources and verification

Images are unchanged example assets from [Microsoft's BiomedCLIP repository](https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224/tree/main/example_data/biomed_image_classification_example_data), pinned to revision `9f341de24bfb00180f1b847274256e9b65a3a32e`.

The structure is [RCSB PDB 1CRN (crambin)](https://www.rcsb.org/structure/1CRN). Cardiac arrays and text prompts were generated locally for testing. `sources.json` records original download URLs and SHA-256 hashes; `verification.json` records the local runner checks. Browser rendering of the protein structure has not been visually verified.
