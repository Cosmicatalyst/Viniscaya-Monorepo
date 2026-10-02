"use client";
import { useEffect, useState } from "react";
import { ArrowDownToLine, MessageSquare, Trash2, FileText, LoaderCircle } from "lucide-react";
import { medicalApi, type ChatMessage } from "@/lib/medical-api";
import { Button } from "@/components/ui/button";
import { AnalysisResult } from "@/components/analysis-result";

type Entry = {id: string; title?: string; updated_at?: string; created_at?: string; category?: string; status?: string; task?: string};
export function SavedWorkspace({ kind, openThread }: { kind: "Threads" | "Library"; openThread: (id: string, messages: ChatMessage[], report_ids?: string[]) => void }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{id: string; output: Record<string, unknown>} | null>(null);
  useEffect(() => {
    let alive = true;
    medicalApi(kind === "Threads" ? "v1/threads" : "v1/jobs").then(data => { if (alive) setEntries(kind === "Threads" ? data.threads : data.jobs.filter((job: Entry) => job.status === "completed")); }).catch(e => {if (alive) setError(e.message);}).finally(() => {if (alive) setLoading(false);});
    return () => {alive = false;};
  }, [kind]);
  async function open(entry: Entry) {
    setError("");
    try {
      const data = await medicalApi(kind === "Threads" ? `v1/threads/${entry.id}` : `v1/jobs/${entry.id}`);
      if (kind === "Threads") openThread(entry.id, data.messages, data.report_ids);
      else setResult({id: entry.id, output: data.result.output});
    } catch (e) {setError(e instanceof Error ? e.message : "Unable to open this item.");}
  }
  async function remove(id: string) {
    try {await medicalApi(`v1/threads/${id}`, {method: "DELETE"}); setEntries(items => items.filter(item => item.id !== id));}
    catch(e) {setError(e instanceof Error ? e.message : "Unable to delete thread.");}
  }
  return <div className="saved-workspace"><header><h1>{kind}</h1><span>{entries.length} saved</span></header>
    {loading ? <LoaderCircle className="animate-spin" size={18} /> : !entries.length ? <p className="saved-empty">{kind === "Threads" ? "Your conversations will appear here." : "Completed analyses are saved here automatically."}</p> : <div className="saved-list">{entries.map(entry => <div key={entry.id}><button onClick={() => void open(entry)}>{kind === "Threads" ? <MessageSquare size={18}/> : <FileText size={18}/>}<span><strong>{entry.title || `${entry.category} · ${entry.task?.replaceAll("_", " ")}`}</strong><small>{new Date(entry.updated_at || entry.created_at || "").toLocaleString()}</small></span></button>{kind === "Threads" ? <Button variant="ghost" size="icon" onClick={() => void remove(entry.id)} aria-label="Delete conversation"><Trash2 size={16}/></Button> : <a href={`/api/medical/v1/jobs/${entry.id}/result`} download aria-label="Download result"><ArrowDownToLine size={16}/></a>}</div>)}</div>}
    {error && <p className="medical-error" role="alert">{error}</p>}
    {result && <section className="medical-result"><header><h2>Saved result</h2><Button variant="ghost" onClick={() => setResult(null)}>Close</Button></header><AnalysisResult output={result.output} jobId={result.id}/></section>}
  </div>;
}
