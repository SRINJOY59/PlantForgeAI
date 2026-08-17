import { useState, useMemo, useEffect, useRef } from "react";
import { FileText, Search, Clock, ShieldCheck, Wrench, FileSearch, Filter, Loader2 } from "lucide-react";
import { getGraph, uploadDocument } from "../../lib/api";

const TYPE_CFG = {
  work_order: { label: "Work Order", Icon: Wrench,     color: "#d97706", bg: "#fef3c7" },
  sop:        { label: "SOP",        Icon: ShieldCheck,color: "#16a34a", bg: "#dcfce7" },
  incident:   { label: "Incident",   Icon: Clock,      color: "#dc2626", bg: "#fee2e2" },
  drawing:    { label: "Drawing",    Icon: Filter,     color: "#7c3aed", bg: "#ede9fe" },
  manual:     { label: "Manual",     Icon: FileText,   color: "#2563eb", bg: "#dbeafe" },
  email:      { label: "Email",      Icon: FileText,   color: "#0284c7", bg: "#e0f2fe" },
};

function docTypeFromName(name) {
  const n = name.toLowerCase();
  if (n.endsWith(".eml") || n.startsWith("email")) return "email";
  if (n.endsWith(".svg") || n.includes("pnid") || n.includes("dwg")) return "drawing";
  if (/\.(png|jpe?g|webp)$/.test(n)) return "drawing";
  if (n.startsWith("sop") || n.includes("procedure")) return "sop";
  if (n.includes("incident") || n.startsWith("ir-")) return "incident";
  if (/\.(csv|xlsx?|tsv)$/.test(n)) return "work_order";
  return "manual";
}

export default function Documents() {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);

  const fileInputRef = useRef(null);

  const loadDocs = () => {
    setLoading(true);
    getGraph().then(data => {
      const { nodes, edges } = data;
      const docNodes = nodes.filter(n => n.label === "Document");
      
      const formattedDocs = docNodes.map(n => {
        // Find connected equipment
        const connectedEdges = edges.filter(e => e.src === n.id || e.dst === n.id);
        const eqIds = connectedEdges.map(e => e.src === n.id ? e.dst : e.src);
        const eqNodes = nodes.filter(x => eqIds.includes(x.id) && x.label === "Equipment");

        // the graph stores filename + content_hash on a Document; the kind is
        // read back off the filename the same way ingestion classified it
        const filename = n.props?.filename || n.surface || n.id;

        return {
          id: n.id,
          title: filename,
          type: docTypeFromName(filename),
          date: "",
          author: "System",
          equipment: eqNodes.map(e => e.surface || e.id),
          tags: [`${connectedEdges.length} links`]
        };
      });
      
      setDocs(formattedDocs);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  };

  useEffect(() => {
    loadDocs();
  }, []);

  const handleUploadClick = () => {
    setUploadError(null);
    setUploadSuccess(false);
    fileInputRef.current.click();
  };

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    setUploadSuccess(false);

    try {
      await uploadDocument(file);
      setUploadSuccess(true);
      loadDocs();
    } catch (err) {
      console.error(err);
      if (err.message.includes("403")) {
        setUploadError("Access Denied: Uploading documents requires the Engineer role.");
      } else {
        setUploadError(err.message || "Failed to upload document.");
      }
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const filtered = useMemo(() =>
    docs.filter(d =>
      (typeFilter === "all" || d.type === typeFilter) &&
      (search === "" || d.title.toLowerCase().includes(search.toLowerCase()) || d.id.toLowerCase().includes(search.toLowerCase()))
    ), [search, typeFilter, docs]);

  return (
    <div className="mx-auto max-w-4xl px-6 py-6 h-full overflow-y-auto">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <FileSearch size={20} style={{ color: "var(--blue)" }} /> Documents
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>
            The raw knowledge base driving the plant brain.
          </p>
        </div>
        <div>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            style={{ display: "none" }}
            accept=".pdf,.md,.txt,.docx,.doc,.html,.csv,.tsv,.xlsx,.xls,.xlsm,.eml,.msg,.svg,.png,.jpg,.jpeg,.webp"
          />
          <button
            onClick={handleUploadClick}
            disabled={uploading}
            className="btn-primary text-xs px-4 flex items-center gap-1.5"
          >
            {uploading ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                Uploading...
              </>
            ) : (
              "Upload Document"
            )}
          </button>
        </div>
      </div>

      {uploadError && (
        <div className="mb-4 text-xs font-semibold text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3">
          ⚠️ {uploadError}
        </div>
      )}

      {uploadSuccess && (
        <div className="mb-4 text-xs font-semibold text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-lg p-3">
          ✓ Document uploaded successfully. The pipeline will now parse, extract, and index it into the plant brain.
        </div>
      )}

      <div className="mb-6 flex items-center gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--muted)" }} />
          <input className="input pl-9" placeholder="Search title, ID, equipment…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div className="flex items-center gap-1.5 rounded-lg p-1 overflow-x-auto whitespace-nowrap scrollbar-hide" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
          <button onClick={() => setTypeFilter("all")}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all ${typeFilter === "all" ? "bg-[var(--bg-panel)] shadow-sm text-brand-600" : "text-[var(--muted)] hover:text-[var(--text)]"}`}>
            All
          </button>
          {Object.entries(TYPE_CFG).map(([k, cfg]) => (
            <button key={k} onClick={() => setTypeFilter(k)}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${typeFilter === k ? "bg-[var(--bg-panel)] shadow-sm" : "hover:bg-[var(--bg-subtle)]"}`}
              style={{ color: typeFilter === k ? cfg.color : "var(--muted)" }}>
              <cfg.Icon size={12} /> {cfg.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-20 text-[var(--muted-lt)]">
          <Loader2 className="animate-spin mr-2" size={20} /> Loading documents...
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.length === 0 && (
             <div className="text-center py-10 text-[var(--muted-lt)] text-sm border rounded-xl border-dashed">
               No documents found.
             </div>
          )}
          {filtered.map(doc => {
            const cfg = TYPE_CFG[doc.type] ?? TYPE_CFG.manual;
            return (
              <div key={doc.id} className="group flex items-start gap-4 rounded-xl p-4 transition-all duration-150 cursor-pointer"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", boxShadow: "0 1px 2px rgba(0,0,0,0.03)" }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--blue-mid)"; e.currentTarget.style.boxShadow = "0 4px 12px rgba(122,84,160,0.06)"; e.currentTarget.style.transform = "translateY(-1px)"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.boxShadow = "0 1px 2px rgba(0,0,0,0.03)"; e.currentTarget.style.transform = "translateY(0)"; }}
              >
                <div className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-lg" style={{ background: cfg.bg }}>
                  <cfg.Icon size={18} style={{ color: cfg.color }} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h3 className="text-sm font-semibold truncate" style={{ color: "var(--text)" }}>{doc.title}</h3>
                    <span className="text-[10px] font-mono" style={{ color: "var(--muted-lt)" }}>{doc.date}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs mb-2.5" style={{ color: "var(--muted)" }}>
                    <span className="font-mono text-[11px] font-medium" style={{ color: "var(--blue)" }}>{doc.id.slice(0, 8)}...</span>
                    <span>·</span>
                    <span>{doc.type}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {doc.equipment.map(eq => (
                      <span key={eq} className="rounded-md px-1.5 py-0.5 text-[10px] font-mono" style={{ background: "var(--bg-subtle)", color: "var(--text-md)", border: "1px solid var(--border)" }}>
                        {eq}
                      </span>
                    ))}
                    {doc.equipment.length > 0 && <div className="h-3 w-px bg-[var(--border)] mx-1" />}
                    {doc.tags.map(t => (
                      <span key={t} className="text-[10px]" style={{ color: "var(--muted-lt)" }}>#{t}</span>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
