"use client";
import { useEffect, useState } from "react";
import { FileText, Copy, Download, LoaderCircle, Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { medicalApi } from "@/lib/medical-api";
import { useReportChat } from "@/components/report-chat-context";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter } from "@/components/ui/sheet";

type Report = {title: string; scope: string; markdown: string; generation_status?: string; generation_error?: string; model?: string; vision_markdown?: string};
export function ReportSheet({ jobId }: {jobId: string}) {
  const openChat = useReportChat();
  const [open, setOpen] = useState(true);
  const [report, setReport] = useState<Report>();
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!open) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {const data = await medicalApi(`v1/jobs/${jobId}/report`);if (!alive) return;setReport(data);if (data.generation_status === "running") timer = setTimeout(() => void refresh(), 2000);}
      catch (e) {if (alive) setError(e instanceof Error ? e.message : "Report unavailable.");}
    }
    void refresh();
    return () => {alive = false;clearTimeout(timer);};
  }, [open, jobId, retry]);
  async function copy() {
    try {await navigator.clipboard.writeText(report?.markdown || "");setCopied(true);}
    catch {setError("Could not copy. Use Download instead.");}
  }
  return <><Button variant="outline" className="report-open" onClick={() => setOpen(true)}><FileText size={15}/>Full report</Button>
    <Sheet open={open} onOpenChange={setOpen}><SheetContent side="right" className="report-sheet">
      <SheetHeader className="report-sheet-header"><span className="report-brand">viniścaya / Report</span><SheetTitle>{report?.title || "Analysis report"}</SheetTitle><SheetDescription>{report?.scope || "Composing from measured results…"} · Unsigned</SheetDescription></SheetHeader>
      <div className="report-sheet-body">
        {report?.generation_status === "running" && <p className="report-loading"><LoaderCircle className="animate-spin" size={16}/>Sushruta-1 is reviewing the imaging findings…</p>}
        {report?.generation_error && <div role="alert"><p className="medical-error">{report.generation_error}</p><Button variant="outline" onClick={async () => {try {await medicalApi(`v1/jobs/${jobId}/report`, {method: "POST"});setRetry(n => n + 1);}catch(e){setError(e instanceof Error ? e.message : "Retry failed.");}}}>Retry generation</Button></div>}
        {report?.generation_status === "completed" && <p className="input-help">Sushruta-1 · Unsigned medical draft</p>}{error ? <div role="alert"><p className="medical-error">{error}</p><Button variant="outline" onClick={() => {setError("");setRetry(n => n+1);}}>Retry</Button></div> : !report || report.generation_status !== "completed" ? <p className="input-help">The medical report will appear when the review completes.</p> : <article className="report-document"><ReactMarkdown remarkPlugins={[remarkGfm]}>{report.markdown}</ReactMarkdown></article>}{report?.vision_markdown && <details className="raw-output"><summary>Raw visual model output</summary><pre>{report.vision_markdown}</pre></details>}</div>
      <SheetFooter className="report-sheet-footer"><span>Clinician review required</span><div><Button variant="outline" onClick={() => {setOpen(false);openChat(jobId);}}>Ask Co-Doc</Button><Button variant="outline" disabled={report?.generation_status !== "completed"} onClick={() => void copy()}>{copied ? <Check size={15}/> : <Copy size={15}/>} {copied ? "Copied" : "Copy report"}</Button><Button nativeButton={false} disabled={report?.generation_status !== "completed"} render={<a href={`/api/medical/v1/jobs/${jobId}/report?download=true`} download/>}><Download size={15}/>Download report</Button></div></SheetFooter>
    </SheetContent></Sheet>
  </>;
}
