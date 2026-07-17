import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

// Matches [doc:ID], [doc:ID p3], [ID], or [ID p3]
// Assuming ID is at least 8 alphanumeric/underscore/dash chars
const CITE_RE = /\[(?:doc:)?([a-zA-Z0-9_-]{8,})(?:\s*p(\d+))?\]/g;

// react-markdown only trusts http/https/irc/mailto/xmpp and rewrites anything
// else to "" - which silently turned every citation into <a href=""> pointing
// at the current page. Let our own scheme through and hand everything else to
// the stock sanitiser, which is the part that stops javascript: URLs.
const urlTransform = (url) =>
  url.startsWith("cite:") ? url : defaultUrlTransform(url);

// Shorten a filename to something that fits inline without losing which file
// it is: keep the stem, drop a long middle. "incident_report_IR-2025-032.md"
// stays readable; a raw content hash never was.
function label(docId, page, names) {
  const name = names?.[docId] || names?.[`doc:${docId}`];
  const base = name
    ? (name.length > 22 ? name.slice(0, 20) + "…" : name)
    : docId.slice(0, 6);
  return base + (page ? `·p${page}` : "");
}

export default function AnswerText({ text, onCite, names }) {
  const processedText = (text || "").replace(CITE_RE, (match, docId, page) => {
    const href = `cite:${docId}${page ? `?p=${page}` : ""}`;
    return `[${label(docId, page, names)}](${href})`;
  });

  return (
    <div className="prose prose-sm max-w-none prose-headings:font-semibold prose-a:text-blue-600 prose-p:leading-relaxed prose-li:my-0.5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={urlTransform}
        components={{
          a: ({ node, href, children, ...props }) => {
            if (href && href.startsWith("cite:")) {
              const idPart = href.slice(5).split("?")[0];
              return (
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    onCite(idPart);
                  }}
                  className="mx-0.5 inline-flex items-center rounded px-1.5 py-0.5 align-baseline font-mono text-[10px] font-bold transition-colors"
                  style={{ background: "#dbeafe", color: "var(--blue)", border: "1px solid #bfdbfe", textDecoration: "none" }}
                  title="View source document"
                >
                  {children}
                </button>
              );
            }
            return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
          }
        }}
      >
        {processedText}
      </ReactMarkdown>
    </div>
  );
}
