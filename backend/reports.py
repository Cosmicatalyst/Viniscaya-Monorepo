"""Evidence-bounded report composition from persisted outputs; no invented findings."""
import math
from datetime import datetime, timezone

REFERENCES = {
    "phikon": "https://huggingface.co/owkin/phikon",
    "biomedclip-radiology": "https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
    "biomedclip-neurology": "https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
    "echonext": "https://github.com/PierreElias/IntroECG/tree/master/7-EchoNext%20Minimodel",
    "qwen-small": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct",
    "pubmedbert": "https://huggingface.co/microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext",
}

def safe(value):
    # Prevent supplied filenames/text from being interpreted as report structure.
    text = str(value).replace("\n", " ").replace("\r", " ")
    for character in "\\`*_{}[]<>#|": text = text.replace(character, "\\" + character)
    return text

def detailed_findings(output, category):
    sections = ["## Problem-oriented assessment"]
    candidates = output.get("candidate_scores", [])
    if candidates:
        first = candidates[0]
        sections += [f"**Leading visual review candidate: {safe(first['label'])}.** Cosine similarity: **{first['score']:.6f}**. This is the most similar supplied prompt, not a diagnosis."]
        if len(candidates) > 1:
            sections += [f"- Difference from next-ranked candidate: {first['score'] - candidates[1]['score']:.6f}. This margin has no validated clinical cutoff."]
        sections += ["### Named candidate inventory — unconfirmed"]
        sections += [f"{i}. **{safe(item['label'])}** — cosine **{item['score']:.6f}**; status: unconfirmed visual-pattern hypothesis. Prompt: {safe(item['prompt'])}." for i, item in enumerate(candidates, 1)]
        sections += [safe(output.get("candidate_basis", "Prompt comparison only."))]
    elif category in {"Cancer", "Radiology", "Neurology"}:
        sections += ["Named visual candidates were not computed for this earlier run. Run a new analysis to obtain pattern comparisons and image metrics."]
    quality = output.get("image_quality")
    if quality:
        sections += ["### Measured image values", f"- Original dimensions: **{quality['width']} × {quality['height']} px** ({quality['megapixels']:.4f} megapixels); color mode: {safe(quality['color_mode'])}.", f"- Mean grayscale intensity: **{quality['intensity_mean']:.3f} / 255**.", f"- Global intensity standard deviation: **{quality['intensity_sd']:.3f} intensity units**.", f"- 5th / 95th intensity percentiles: **{quality['intensity_p05']:.3f} / {quality['intensity_p95']:.3f}**.", f"- Grayscale entropy: **{quality['entropy_bits']:.4f} bits**.", f"- Dark pixels (≤5): **{quality['dark_pixel_percent']:.3f}%**; bright pixels (≥250): **{quality['bright_pixel_percent']:.3f}%**.", f"- Gradient energy: **{quality['gradient_energy']:.3f} squared intensity units**.", safe(quality['measurement_basis']), "### Named technical problems"]
        if quality["problems"]:
            sections += [f"- **{safe(p['label'])}**: {p['value']} {safe(p['unit'])}. Basis: {safe(p['basis'])}" for p in quality["problems"]]
        else: sections += ["- No flags triggered by the limited small-image / low-global-contrast heuristics. This does not establish adequate clinical image quality."]
    text = output.get("text_measurements")
    if text:
        sections += ["### Supplied clinical values", f"Input length: {text['words']} words / {text['characters']} characters. Values below are extracted from supplied text, not newly measured or verified."]
        if text["measurements"]:
            sections += [f"- **{safe(item['label'])}**: **{safe(item['value'])} {safe(item['unit'])}**. Source excerpt: {safe(item['source'])}. Status: supplied; clinical interpretation not established." for item in text["measurements"]]
        else: sections += ["- No supported, explicitly formatted vital signs or laboratory values were found. Missing values are not inferred from generated text."]
        sections += ["### Supplied problems"]
        sections += [f"- **{safe(p['label'])}**: {safe(p['description'])}. {safe(p['basis'])}." for p in text["problems"]] or ["- No explicit assessment/problem/diagnosis line was supplied."]
        missing = [name for name in ["Blood pressure", "Heart rate", "Respiratory rate", "Oxygen saturation", "Temperature"] if name not in {v['label'] for v in text['measurements']}]
        sections += ["- Unrecorded vital fields: " + (", ".join(missing) or "All supported vital fields present; values still require verification.")]
    domains = {
        "Cancer": ["Tumor presence", "Histologic diagnosis", "Tumor grade", "Invasion", "Margins", "Stage", "Molecular markers"],
        "Radiology": ["Lesion location", "Lesion size", "Lung/pleural findings", "Fracture confirmation", "Longitudinal change", "Clinical impression"],
        "Neurology": ["Lesion location and volume", "Diffusion restriction", "Hemorrhage confirmation", "Mass effect", "Ventricular measurements", "EEG findings"],
        "General": ["Confirmed diagnosis", "Differential diagnosis", "Medication safety", "Treatment plan", "Prognosis"],
    }
    if category in domains:
        sections += ["### Clinical feature coverage", *[f"- **{name}**: not measured / not established by this runner." for name in domains[category]]]
    return sections

def compose(job, result, category, model_name):
    output = result.get("output", {})
    inputs = result.get("input", {})
    synthetic = inputs.get("synthetic_label", False)
    scope = "Synthetic test report" if synthetic else "Research analysis report"
    sections = [f"# {category} analysis report", f"**{scope} · Clinician review required**", "## Summary", "This report documents the available model output and its boundaries. It does not establish a patient diagnosis, exclude disease, or authorize treatment.", "## Study and provenance", f"- Analysis ID: `{job['id']}`", f"- Performed: {job['created_at']}", f"- Report composed: {datetime.now(timezone.utc).isoformat()}", f"- Model: {safe(model_name)}", f"- Task: {safe(job['task'])}", "- Status: Completed", "- Patient identity, age, sex, indication, history, examination, and clinician assessment: Not provided."]
    if inputs:
        sections += ["- Source files: " + (", ".join(safe(name) for name in inputs.get("files", [])) or "No file; text/sequence input")]
        if inputs.get("text"): sections += ["- Supplied text/context (not independently verified): " + safe(inputs["text"][:16000])]
    else: sections += ["- Input provenance: Not recorded for this earlier analysis."]
    if synthetic: sections += ["- The source filename marks this as synthetic. Outputs have no patient-level clinical meaning."]
    if output.get("additional_model"): sections += ["- Additional model: " + safe(output["additional_model"])]
    sections += detailed_findings(output, category)
    sections += ["## Technical findings"]
    vector = output.get("embedding")
    if isinstance(vector, list) and vector:
        values = [v for v in vector if isinstance(v, (int, float)) and math.isfinite(v)]
        sections += [f"- Embedding dimensions returned: {len(vector)}", f"- Finite numeric entries: {len(values)} / {len(vector)}"]
        if values:
            mean = sum(values)/len(values)
            ordered = sorted(values)
            median = (ordered[(len(values)-1)//2] + ordered[len(values)//2])/2
            sections += [f"- Vector L2 norm: {math.sqrt(sum(v*v for v in values)):.6f}", f"- Value range: {min(values):.6f} to {max(values):.6f}", f"- Mean / median: {mean:.6f} / {median:.6f}", f"- Population standard deviation: {math.sqrt(sum((v-mean)**2 for v in values)/len(values)):.6f}", f"- Positive / negative / zero dimensions: {sum(v>0 for v in values)} / {sum(v<0 for v in values)} / {sum(v==0 for v in values)}"]
        sections += ["- Representation only: these numbers have no direct disease severity, probability, or diagnostic threshold."]
    similarity = output.get("image_text_similarity")
    if isinstance(similarity, (int, float)): sections += [f"- Image/text cosine similarity: {similarity:.6f}", "- Similarity measures representation alignment; it is not diagnostic confidence or a disease probability."]
    predictions = output.get("predictions", [])
    if predictions:
        sections += ["### Complete model score inventory", "Endpoint names are model targets, not confirmed findings. No validated decision thresholds or confidence intervals were supplied."]
        sections += [f"- **{safe(item['label'])}**: raw score {item['score']:.6f} ({item['score']*100:.2f}% on the model score scale)." for item in predictions]
        sections += ["Scores must not be converted into a positive/negative result, severity category, or individualized disease probability without appropriate validation."]
    if output.get("text"):
        sections += ["### Generated draft", "The following is model-generated text, not independently verified medical evidence:", *["> " + line for line in output["text"].splitlines()]]
    if output.get("note"): sections += ["- Runner note: " + safe(output["note"])]
    boundaries = {
        "Cancer": "The pathology runner computes image-patch embeddings. It does not provide tumor detection, tissue classification, grading, staging, margin status, molecular markers, prognosis, or whole-slide assessment.",
        "Radiology": "The image runner computes biomedical representations and optional text similarity. It does not establish radiographic abnormalities, lesion measurements, diagnostic impressions, or longitudinal change; no calibrated interpretation head is installed.",
        "Neurology": "The runner analyzes a single 2D image representation. It does not evaluate the complete MRI study, sequences, brain anatomy, lesions, EEG signals, neurological examination, or disease diagnosis.",
        "Cardiac": "The minimodel returns 12 research scores from prepared ECG and tabular arrays. It does not directly measure echocardiographic anatomy, ejection fraction, valve severity, pressures, rhythm, or clinical diagnosis. A target label such as LVEF ≤45% is not an observed LVEF measurement.",
        "General": "The compact local language model produces draft text. Clinical accuracy, literature currency, references, medication choices, and management recommendations are not verified by this pipeline. Text embeddings are representations, not clinical findings.",
        "Proteins": "Predicted or uploaded coordinates do not establish functional activity, pathogenicity, binding affinity, biological efficacy, or clinical suitability.",
    }
    sections += ["## Interpretation and impression", boundaries.get(category, "Interpretation is limited to the reported output."), "**Clinical impression: Indeterminate from this analysis alone.** A normal result, disease exclusion, treatment decision, or prognosis cannot be established.", "## Input quality and uncertainty", "- Pipeline completion confirms execution, not clinical validity or adequate acquisition quality.", "- Patient identity, clinical indication, acquisition metadata, preprocessing provenance, and external validation have not been independently verified.", "- Sensitivity, specificity, calibration, out-of-distribution status, confidence intervals, and population suitability are not available for this run."]
    if category == "Cardiac": sections += ["- Accepted contract: one waveform array (1,1,2500,12) and one tabular array (1,7), finite values. Shape checks cannot prove correct lead order, units, filtering, normalization, feature order, or patient eligibility."]
    elif category in {"Cancer", "Radiology", "Neurology"}: sections += ["- Image readability does not verify focus, stain, orientation, diagnostic coverage, modality suitability, or absence of acquisition artifacts."]
    sections += ["## Review checklist", "1. Confirm the input belongs to the intended study and identify whether it is synthetic or real.", "2. Review original data, acquisition quality, preprocessing, and the model's intended use.", "3. Add the clinical indication, relevant history, examination, and applicable independent reference findings.", "4. Have an appropriately qualified clinician establish any clinical findings and impression from the primary study.", "5. Do not initiate, withhold, or change treatment solely from these unvalidated outputs.", "## Missing information", "Patient identifiers; referral indication; symptoms and time course; examination and vital signs; medications; relevant laboratory results; complete source study; validated thresholds; independent interpretation; reviewer identity and sign-off.", "## Model reference"]
    if job["model_id"] in REFERENCES: sections += [f"[Model documentation]({REFERENCES[job['model_id']]})"]
    if output.get("additional_model"): sections += [f"[Additional pattern comparison model]({REFERENCES['biomedclip-radiology']})"]
    sections += ["## Reviewer sign-off", "Reviewer: ____________________  Date: ____________________", "Verified clinical findings and final impression: Not supplied. This report remains an unsigned research draft."]
    return {"title": f"{category} analysis report", "scope": scope, "markdown": "\n\n".join(sections), "clinical_status": "unverified", "job_id": job["id"]}
