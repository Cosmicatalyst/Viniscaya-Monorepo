"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowRight, LoaderCircle, Upload } from "lucide-react";
import { SourcePreviews } from "@/components/source-previews";
import { AnalysisResult } from "@/components/analysis-result";
import { medicalApi as api } from "@/lib/medical-api";
import { ProteinViewer } from "@/components/protein-viewer";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type Model = { id: string; name: string; category: string; modality: string; tasks: string[]; status: string; reason: string };
type Job = { id: string; status: string; error?: string; result?: { output: Record<string, unknown> } };

export function SpecialtyWorkspace({ category }: { category: string }) {
  const [models, setModels] = useState<Model[]>([]);
  const [selected, setSelected] = useState("");
  const [task, setTask] = useState("");
  const [text, setText] = useState("");
  const [sequence, setSequence] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sampleNotice, setSampleNotice] = useState("");
  const [sampleName, setSampleName] = useState("");
  const [previewIds, setPreviewIds] = useState<string[]>([]);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [sampleIds, setSampleIds] = useState<string[]>([]);
  const [samplePdb, setSamplePdb] = useState<string>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const mounted = useRef(true);
  const model = models.find(item => item.id === selected);

  useEffect(() => {
    mounted.current = true;
    api(`v1/models?category=${encodeURIComponent(category)}`).then(data => {
      if (!mounted.current) return;
      setModels(data.models); setSelected(data.models[0]?.id || ""); setTask(data.models[0]?.tasks[0] || "");
    }).catch(error => { if (mounted.current) setError(error.message); }).finally(() => { if (mounted.current) setLoading(false); });
    return () => { mounted.current = false; };
  }, [category]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try { const result = await api(`v1/jobs/${job.id}`); if (!cancelled) setJob(result); }
      catch (error) { if (!cancelled) { setError(error instanceof Error ? error.message : "Could not check the job."); setJob(previous => previous ? { ...previous, status: "unavailable" } : null); setBusy(false); } }
    }, 1500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [job]);

  async function submit() {
    if (!model || busy) return;
    setBusy(true); setError(""); setJob(null);
    try {
      const ids: string[] = [...sampleIds, ...previewIds];
      for (const file of previewIds.length ? [] : files) {
        const form = new FormData(); form.set("file", file);
        const upload = await api("v1/files", { method: "POST", body: form }); ids.push(upload.id);
      }
      const created = await api(category === "Proteins" ? "v1/inference" : "v1/cases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(category === "Proteins" ? { model_id: model.id, task, text: text || null, sequence: sequence || null, file_ids: ids } : { category, text, file_ids: ids }) });
      if (mounted.current) setJob(created);
    } catch (error) { if (mounted.current) setError(error instanceof Error ? error.message : "Unable to start inference."); }
    finally { if (mounted.current) setBusy(false); }
  }

  async function trySample(variant = "default") {
    setBusy(true);setError("");setJob(null);
    try {
      const data = await api("v1/samples", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({category, variant})});
      setSampleNotice(data.sample_notice || data.notice);setSampleName(data.sample_name || data.name || "");setSampleIds(data.sample_file_ids || []);
      if (data.kind === "structure") setSamplePdb(data.pdb);
      else {setText(data.sample_notice);setPreviewIds([]);setFiles([]);setJob(data);}
    } catch (error) {setError(error instanceof Error ? error.message : "Could not load sample.");}
    finally {setBusy(false);}
  }

  const running = busy || previewBusy || !!job && ["queued", "running"].includes(job.status);
  const output = job?.result?.output;
  return <div className="medical-workspace">
    <div className="medical-heading"><h1>{category}</h1><span>Case analysis</span></div>
    <div className="sample-actions"><Button variant="outline" disabled={running} onClick={() => void trySample()}>{category === "Proteins" ? "View sample structure" : "Try sample"}</Button>{category === "Radiology" && <Button variant="ghost" disabled={running} onClick={() => void trySample("bone")}>Bone X-ray sample</Button>}{category === "Cancer" && <Button variant="ghost" disabled={running} onClick={() => void trySample("adenocarcinoma")}>Second tissue sample</Button>}</div>
    {sampleNotice && <p className="input-help" role="status">{sampleNotice}</p>}
    {category === "Proteins" && <ProteinViewer pdb={typeof output?.pdb === "string" ? output.pdb : samplePdb} />}
    {loading ? <p className="medical-loading"><LoaderCircle size={16} className="animate-spin" />Connecting to Python API…</p> : <>
      {model && <><div className={`model-status ${model.status === "configured" ? "model-configured" : ""}`}><span />{category === "Proteins" ? model.name : "Sushruta-1"}<small>{category === "Proteins" ? model.reason : "Upload source files to begin"}</small></div>
        <div className="medical-inputs">
          {category === "Proteins" ? <label>Protein analysis<select aria-label="Protein analysis" disabled={running} value={selected} onChange={event => {const next = models.find(item => item.id === event.target.value);setSelected(event.target.value);setTask(next?.tasks[0] || "");setJob(null);}}>{models.map(item => <option key={item.id} value={item.id}>{item.id === "esmfold" ? "Predict 3D structure · ESMFold" : "Analyze sequence · ESM-2"}</option>)}</select>Protein sequence<Textarea value={sequence} disabled={running} onChange={event => setSequence(event.target.value)} placeholder="MKTAYIAKQRQISFVKSHFSRQ…" maxLength={selected === "esmfold" ? 256 : 1022} /></label> : <>
            <label className="medical-upload"><Upload size={20}/><span>{files.length ? files.map(file => file.name).join(", ") : sampleName || "Upload case files"}</span><small>Up to 8 files · 100 MB each · 200 MB total</small><input type="file" multiple disabled={running} accept=".png,.jpg,.jpeg,.tif,.tiff,.pdf,.txt,.csv,.docx,.dcm,.nii,.nii.gz,.npz" onChange={event => {const picked = Array.from(event.target.files || []); if (picked.length > 8 || picked.some(file => file.size > 100 * 1024 * 1024) || picked.reduce((n, file) => n + file.size, 0) > 200 * 1024 * 1024) {setError("Choose up to 8 files, 100 MB each and 200 MB total.");return;}setFiles(picked);setPreviewIds([]);setSampleIds([]);setSampleName("");setSampleNotice("");setError("");}}/></label>
            <label>Clinical context (optional)<Textarea value={text} disabled={running} onChange={event => setText(event.target.value)} placeholder="History, symptoms or existing findings…" maxLength={16000}/></label>
            <p className="input-help">Images, reports and scan previews contribute to one report. Selected pages and slices are listed in source coverage.{category === "Neurology" && " 3D tumor regions require aligned 1 mm NIfTI files named T1ce, T1, T2 and FLAIR."}{category === "Cardiac" && " EchoNext requires prepared NPZ: waveforms (1,1,2500,12), tabular (1,7)."}</p>
          </>}
        </div><Button className="medical-run" onClick={submit} disabled={running || (files.length > 0 && previewIds.length !== files.length) || (category === "Proteins" ? model.status !== "configured" : !files.length && !text.trim())}>{running ? <LoaderCircle size={16} className="animate-spin"/> : <ArrowRight size={16}/>} {running ? "Preparing evidence…" : category === "Proteins" ? selected === "esmfold" ? "Predict 3D structure" : "Analyze sequence" : "Generate report"}</Button>
      </>}
    </>}
    {category !== "Proteins" && (files.length > 0 || sampleIds.length > 0) && <SourcePreviews key={files.length ? files.map(file => `${file.name}-${file.size}-${file.lastModified}`).join("|") : sampleIds.join("|")} files={files} fileIds={sampleIds} onUploaded={setPreviewIds} onBusy={setPreviewBusy}/>}
    {error && <p className="medical-error" role="alert">{error}</p>}
    {job?.status === "unavailable" && <Button className="medical-run" onClick={() => { setError(""); setJob({ ...job, status: "queued" }); }}>Retry job status</Button>}
    {job && <section className="medical-result" aria-live="polite"><header><h2>Result</h2><span>{job.status}</span>{job.status === "completed" && <a href={`/api/medical/v1/jobs/${job.id}/result`} download><ArrowDownToLine size={14} />Download</a>}</header>{job.status === "failed" && <p className="medical-error">{job.error}</p>}{output && <AnalysisResult output={output} jobId={job.id} />}</section>}
  </div>;
}

