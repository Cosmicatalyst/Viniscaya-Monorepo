"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useReportChat } from "@/components/report-chat-context";
import { Button } from "@/components/ui/button";
import { ReportSheet } from "@/components/report-sheet";

export function AnalysisResult({ output, jobId }: { output: Record<string, unknown>; jobId?: string }) {
  const openChat = useReportChat();
  const vector = Array.isArray(output.embedding) ? output.embedding.filter((n): n is number => typeof n === "number").slice(0, 32) : [];
  const maximum = Math.max(...vector.map(Math.abs), .001);
  const predictions = Array.isArray(output.predictions) ? output.predictions as {label: string; score: number}[] : [];
  const candidates = Array.isArray(output.candidate_scores) ? output.candidate_scores as {label: string; score: number}[] : [];
  const quality = output.image_quality as {width: number; height: number; intensity_sd: number; entropy_bits: number; problems: {label: string; value: number; unit: string}[]} | undefined;
  const textValues = output.text_measurements as {measurements: {label: string; value: string; unit: string}[]; problems: {description: string}[]} | undefined;
  const regions = Array.isArray(output.regions) ? output.regions as {label: string; voxel_count: number; predicted_volume_ml: number}[] : [];
  const sources = Array.isArray(output.sources) ? output.sources as {source: string; name: string; status: string; error?: string; coverage?: string[]; text_measurements?: Record<string, unknown>; outputs?: Record<string, unknown>[]}[] : [];
  return <div className="analysis-output">
    {jobId && <div className="analysis-actions"><ReportSheet key={jobId} jobId={jobId}/><Button variant="outline" onClick={() => openChat(jobId)}>Ask Co-Doc</Button></div>}
    {jobId && <details className="raw-output"><summary>Raw model outputs</summary><pre>{JSON.stringify(output, null, 2)}</pre><a href={`/api/medical/v1/jobs/${jobId}/result`} download>Download full analysis JSON</a></details>}
    {!!regions.length && <section className="candidate-results"><h3>Predicted MRI regions</h3><div className="clinical-value-list">{regions.map(item => <div key={item.label}><span>{item.label}</span><strong>{item.predicted_volume_ml.toFixed(3)} mL</strong></div>)}</div><p>Segmentation-derived estimates · unconfirmed tissue findings</p></section>}
    {jobId && sources.some(source => source.outputs?.some(item => typeof item.mask_file === "string")) && <a className="input-help" href={`/api/medical/v1/jobs/${jobId}/segmentation`} download>Download predicted MRI regions (.nii.gz)</a>}
    {!!sources.length && <section className="case-sources"><h3>Source evidence</h3>{sources.map(source => <details key={source.source} className="case-source"><summary><strong>{source.source} · {source.name}</strong><span>{source.status}</span></summary>{source.error && <p className="medical-error">{source.error}</p>}{source.coverage?.map((note, index) => <p key={index} className="input-help">{note}</p>)}{source.text_measurements && <AnalysisResult output={{text_measurements: source.text_measurements}}/>}{source.outputs?.map((item,index) => <div key={index}>{typeof item.unavailable === "string" ? <p className="medical-error">{item.unavailable}</p> : <AnalysisResult output={{predictions: item.predictions, text_measurements: item.text_measurements, regions: item.regions, note: item.note}}/>}</div>)}</details>)}</section>}
    {!!candidates.length && <section className="candidate-results"><h3>Visual review candidates</h3><p>Exploratory prompt similarity · unconfirmed, not disease probabilities</p><div className="prediction-list">{candidates.map(item => <div key={item.label}><span>{item.label}</span><div><i style={{width: `${Math.max(0,Math.min(1,(item.score+1)/2))*100}%`}}/></div><strong>{item.score.toFixed(4)}</strong></div>)}</div></section>}
    {quality && <div className="quality-values"><span><strong>{quality.width} × {quality.height}</strong>Source pixels</span><span><strong>{quality.intensity_sd.toFixed(2)}</strong>Intensity SD</span><span><strong>{quality.entropy_bits.toFixed(3)}</strong>Entropy · bits</span></div>}
    {quality?.problems.map(item => <p className="result-note" key={item.label}>{item.label}: {item.value} {item.unit}</p>)}
    {!!textValues?.measurements.length && <section className="candidate-results"><h3>Supplied clinical values</h3><div className="clinical-value-list">{textValues.measurements.map((item,i) => <div key={i}><span>{item.label}</span><strong>{item.value} {item.unit}</strong></div>)}</div><p>Extracted from input · not independently verified</p></section>}
    {typeof output.text === "string" && <div className="assistant-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{output.text}</ReactMarkdown></div>}
    {!!vector.length && <><p className="result-metric"><strong>{String(output.dimensions)}</strong> embedding dimensions</p><div className="embedding-chart" role="img" aria-label="First 32 embedding values">{vector.map((value, i) => <div key={i} style={{ height: `${Math.max(3, Math.abs(value) / maximum * 100)}%`, opacity: value < 0 ? .45 : 1 }} title={`Dimension ${i + 1}: ${value.toFixed(4)}`} />)}</div><small>First 32 dimensions · representation values</small></>}
    {typeof output.image_text_similarity === "number" && <p className="result-metric"><strong>{output.image_text_similarity.toFixed(3)}</strong> image / text cosine similarity</p>}
    {!!predictions.length && <div className="prediction-list">{predictions.map(item => <div key={item.label}><span>{item.label}</span><div><i style={{width: `${Math.max(0, Math.min(1, item.score)) * 100}%`}} /></div><strong>{(item.score * 100).toFixed(1)}%</strong></div>)}</div>}
    {typeof output.note === "string" && <p className="result-note">{output.note}</p>}
  </div>;
}
