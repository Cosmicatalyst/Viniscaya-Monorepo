import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function CoDocResponse({ content }: { content: string; pending?: boolean; startedAt?: number; duration?: number }) {
  const answerMarker = content.indexOf("[[ANSWER]]");
  const answer = answerMarker >= 0 ? content.slice(answerMarker + 10).trim() : content.startsWith("[[SUMMARY]]") ? "" : content;
  return answer ? <div className="co-doc-answer"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>,
    img: () => null,
  }}>{answer}</ReactMarkdown></div> : null;
}
