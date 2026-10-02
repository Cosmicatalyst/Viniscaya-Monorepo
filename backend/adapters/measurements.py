"""Measured technical descriptors and verbatim clinical values; no diagnoses."""
import re

def image_metrics(image):
    import numpy as np
    gray = np.asarray(image.convert("L").resize((256, 256)), dtype=np.float32)
    histogram = np.bincount(gray.astype(np.uint8).ravel(), minlength=256).astype(float)
    probabilities = histogram[histogram > 0] / histogram.sum()
    std = float(gray.std())
    problems = []
    if min(image.size) < 224:
        problems.append({"label": "Small source image", "value": min(image.size), "unit": "px on shortest side", "basis": "Short side below the encoder's 224 px input; resizing adds no detail."})
    if std < 10:
        problems.append({"label": "Low global contrast", "value": round(std, 3), "unit": "8-bit intensity SD", "basis": "Technical heuristic: SD below 10. This is not a validated clinical quality threshold."})
    return {"width": image.width, "height": image.height, "color_mode": image.mode,
            "megapixels": round(image.width * image.height / 1e6, 4),
            "intensity_mean": round(float(gray.mean()), 3), "intensity_sd": round(std, 3),
            "intensity_p05": round(float(np.percentile(gray, 5)), 3), "intensity_p95": round(float(np.percentile(gray, 95)), 3),
            "entropy_bits": round(float(-(probabilities * np.log2(probabilities)).sum()), 4),
            "dark_pixel_percent": round(float((gray <= 5).mean() * 100), 3),
            "bright_pixel_percent": round(float((gray >= 250).mean() * 100), 3),
            "gradient_energy": round(float((np.diff(gray, axis=0)**2).mean() + (np.diff(gray, axis=1)**2).mean()), 3),
            "measurement_basis": "Intensity metrics measured on a 256×256 grayscale copy, range 0–255. Gradient energy is a technical detail descriptor, not validated sharpness.",
            "problems": problems}

def text_metrics(text):
    text = text or ""
    patterns = [
        ("Blood pressure", r"(?:blood pressure|\bBP)\s*[:=]?\s*(\d{2,3}\s*/\s*\d{2,3})\s*(mmHg)?", "mmHg"),
        ("Heart rate", r"(?:heart rate|\bHR|\bpulse)\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)\s*(bpm|beats/min)?", "bpm"),
        ("Respiratory rate", r"(?:respiratory rate|\bRR)\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)\s*(/min|breaths/min)?", "breaths/min"),
        ("Oxygen saturation", r"(?:SpO2|SpO₂|oxygen saturation)\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)\s*(%)?", "%"),
        ("Temperature", r"(?:temperature|\btemp)\s*[:=]?\s*(\d{2,3}(?:\.\d+)?)\s*(°?C|°?F|celsius|fahrenheit)\b", None),
        ("Glucose", r"(?:glucose)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(mg/dL|mmol/L)", None),
        ("Hemoglobin", r"(?:hemoglobin|haemoglobin|\bHb)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(g/dL|g/L)", None),
        ("Creatinine", r"(?:creatinine)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(mg/dL|µmol/L|umol/L)", None),
    ]
    measurements = []
    for label, pattern, conventional in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if match.end() < len(text) and text[match.end()] in "0123456789.":
                continue
            measurements.append({"label": label, "value": match.group(1), "unit": match.group(2) or "not supplied", "source": match.group(0), "unit_supplied": bool(match.group(2))})
    problems = [{"label": "Assessment supplied in text", "description": m.group(1).strip(), "basis": "Verbatim input; not independently verified"} for m in re.finditer(r"^\s*(?:assessment|problem|diagnosis)\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE) if m.group(1).strip().lower() not in {"not supplied.", "not supplied", "unknown", "none", "not provided"}]
    return {"characters": len(text), "words": len(text.split()), "measurements": measurements, "problems": problems}

PATTERNS = {
    "Cancer": [("Adenocarcinoma-like histology", "adenocarcinoma histopathology"), ("Squamous carcinoma-like histology", "squamous cell carcinoma histopathology"), ("Adipose tissue", "adipose tissue histopathology"), ("Fibrous stroma", "fibrous stromal tissue histopathology"), ("Lymphocyte-rich tissue", "lymphocyte rich tissue histopathology"), ("Glandular tissue", "glandular tissue histopathology"), ("Necrotic tissue", "necrotic tissue histopathology")],
    "Radiology": [("Lung opacity pattern", "chest X-ray with lung opacity"), ("Pleural fluid pattern", "chest X-ray with pleural effusion"), ("Pneumothorax pattern", "chest X-ray with pneumothorax"), ("Enlarged cardiac silhouette", "chest X-ray with cardiomegaly"), ("Chest without obvious abnormality", "normal chest X-ray"), ("Bone fracture pattern", "bone X-ray with a fracture"), ("Bone without obvious fracture", "normal bone X-ray")],
    "Neurology": [("Mass-like brain MRI pattern", "brain MRI with a mass lesion"), ("Hemorrhage-like imaging pattern", "brain MRI showing hemorrhage"), ("Ischemia-like imaging pattern", "brain MRI with ischemic stroke"), ("Ventricular enlargement pattern", "brain MRI with enlarged ventricles"), ("White matter signal pattern", "brain MRI with white matter hyperintensities"), ("Brain without obvious abnormality", "normal brain MRI")],
}
