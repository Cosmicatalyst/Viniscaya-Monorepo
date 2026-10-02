"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUp, Square, Plus } from "lucide-react";
import { CoDocResponse } from "@/components/co-doc-response";
import { medicalApi, type ChatMessage } from "@/lib/medical-api";

export function CoDoc({ initialThread }: { initialThread?: {id: string; messages: ChatMessage[]; report_ids?: string[]} }) {
  const [draft, setDraft] = useState("");
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>(initialThread?.messages || []);
  const [reportIds, setReportIds] = useState<string[]>(initialThread?.report_ids || []);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [reports, setReports] = useState<{id: string; category: string; created_at: string}[]>([]);
  const threadId = useRef(initialThread?.id || "");
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => {abort.current?.abort();}, []);
  async function save(messages: ChatMessage[], attachments = reportIds) {
    if (!threadId.current) threadId.current = crypto.randomUUID().replaceAll("-", "");
    await medicalApi(`v1/threads/${threadId.current}`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({report_ids: attachments, messages: messages.filter(item => item.content.trim()).slice(-40).map(({role,content}) => ({role,content}))})});
  }
  function attachReports(ids: string[]) {
    setReportIds(ids);
    if (history.length) void save(history, ids).catch(error => setMessage(error instanceof Error ? error.message : "Could not save report attachments."));
  }
  const [pending, setPending] = useState(false);
  const conversation = useRef<HTMLDivElement>(null);
  useEffect(() => {
    conversation.current?.scrollTo({ top: conversation.current.scrollHeight, behavior: "smooth" });
  }, [history]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim() || pending) return;
    const question = draft.trim();
    // This runs only in the submit event handler, never during rendering.
    // eslint-disable-next-line react-hooks/purity
    const startedAt = Date.now();
    const messages = [...history.filter(item => item.content.trim()), { role: "user" as const, content: question }];
    setPending(true);
    setMessage("");
    setDraft("");
    setHistory([...messages, { role: "assistant", content: "", startedAt }]);
    abort.current = new AbortController();
    try {
      await save(messages);
      const response = await fetch("/api/chat", { method: "POST", signal: abort.current.signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ report_ids: reportIds, messages: messages.slice(-39).map(({ role, content }) => ({ role, content })) }) });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || "Unable to send your question.");
      }
      if (!response.body) throw new Error("No response received.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "", content = "", completed = false;
      function processLine(line: string) {
        if (!line.startsWith("data:")) return;
        const value = line.slice(5).trim();
        if (!value) return;
        if (value === "[DONE]") { completed = true; return; }
        const data = JSON.parse(value);
        if (data.error) throw new Error("The assistant could not finish its response. Please try again.");
        if (data.type === "thinking_token") return;
        if (data.type === "workflow_complete" || data.type === "final_response") {
          if (!content && typeof data.content === "string") content = data.content;
          completed = true;
        }
        const delta = data.choices?.[0]?.delta?.content ?? (data.type === "token" ? data.content : data.token);
        if (typeof delta === "string") {
          content += delta;
          setHistory([...messages, { role: "assistant", content, startedAt }]);
        }
      }
      try {
        while (!completed) {
          const { value, done } = await reader.read();
          buffer += decoder.decode(value, { stream: !done });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) processLine(line);
          if (done) { if (buffer) processLine(buffer); break; }
        }
        if (!completed) throw new Error("The response was interrupted. Please try again.");
        if (!content.trim()) throw new Error("The assistant returned an empty response.");
        setHistory([...messages, { role: "assistant", content, startedAt, duration: Math.floor((Date.now() - startedAt) / 1000) }]);
        await save([...messages, {role: "assistant", content}]);
      } finally { await reader.cancel().catch(() => {}); }
    } catch (error) {
      setMessage(error instanceof Error && error.name === "AbortError" ? "Response stopped." : error instanceof Error ? error.message : "Unable to send your question.");
    } finally { setPending(false); }
  }

  return (
    <section className={`co-doc-workspace ${history.length ? "co-doc-conversation" : ""}`} aria-labelledby="co-doc-title">
      {!!history.length && <button className="new-conversation" disabled={pending} onClick={() => {setHistory([]);setReportIds([]);threadId.current = "";setMessage("");}}><Plus size={15}/>New conversation</button>}
      <div className="co-doc-center">
        <h1 id="co-doc-title" className={history.length ? "sr-only" : undefined}>How can I support your practice today?</h1>
        {history.length > 0 && <div ref={conversation} className="co-doc-messages" aria-live="polite" aria-busy={pending}>{history.map((item, index) => <div key={index} className={`co-doc-bubble co-doc-${item.role}`}><span className="sr-only">{item.role === "user" ? "You" : "Co-Doc"}: </span>{item.role === "assistant" ? <CoDocResponse content={item.content} pending={pending && index === history.length - 1} startedAt={item.startedAt} duration={item.duration} /> : item.content}</div>)}</div>}
        <div className="chat-reports">
          {reportIds.map(id => <span className="report-chip" key={id}>Report {id.slice(0,6)}<button disabled={pending} aria-label="Remove attached report" onClick={() => attachReports(reportIds.filter(item => item !== id))}>×</button></span>)}
          <button type="button" disabled={pending} onClick={async () => {setPickerOpen(open => !open);try {const data = await medicalApi("v1/jobs");setReports(data.jobs.filter((job: {status: string}) => job.status === "completed"));}catch(e){setMessage(e instanceof Error ? e.message : "Could not load reports.");}}}><Plus size={14}/>Attach report</button>
        </div>
        {pickerOpen && <div className="report-picker">{!reports.length ? <p>No completed reports available.</p> : reports.map(report => <button key={report.id} disabled={pending || reportIds.includes(report.id) || reportIds.length >= 4} onClick={() => {attachReports([...reportIds,report.id]);setPickerOpen(false);}}>{report.category} · {new Date(report.created_at).toLocaleDateString()} · {report.id.slice(0,6)}</button>)}<small>Up to four reports per conversation.</small></div>}
        <form className="co-doc-composer" onSubmit={submit}>
          <label htmlFor="co-doc-question" className="sr-only">Your question for Co-Doc</label>
          <textarea id="co-doc-question" disabled={pending} maxLength={12000} rows={1} value={draft} onChange={event => { setDraft(event.target.value); setMessage(""); }} placeholder="Ask a clinical question…" onKeyDown={event => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }} />
          <button className="co-doc-send" type={pending ? "button" : "submit"} onClick={pending ? () => abort.current?.abort() : undefined} disabled={!pending && !draft.trim()} aria-label={pending ? "Stop response" : "Send question"}>{pending ? <Square size={14} fill="currentColor" /> : <ArrowUp size={20} strokeWidth={2} />}</button>
        </form>
        {message && <p className="co-doc-status" role="status">{message}</p>}
      </div>
    </section>
  );
}

