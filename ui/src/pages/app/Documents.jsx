import { useState } from "react";
import { CheckCircle2, Loader2, UploadCloud } from "lucide-react";
import { ingest } from "../../lib/api";

export default function Documents() {
  const [items, setItems] = useState([]);
  const [dragging, setDragging] = useState(false);

  async function handleFiles(fileList) {
    const files = Array.from(fileList);
    for (const file of files) {
      const id = crypto.randomUUID();
      setItems((prev) => [{ id, name: file.name, status: "uploading" }, ...prev]);
      try {
        await ingest(file);
        update(id, "accepted");
      } catch {
        update(id, "failed");
      }
    }
  }

  function update(id, status) {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, status } : it)));
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-6">
      <h1 className="mb-1 text-lg font-semibold">Documents</h1>
      <p className="mb-5 text-sm muted">
        Drop a work order, P&ID, SOP, manual, email or photo — it flows into the
        graph within seconds.
      </p>

      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-10 text-center transition-colors ${dragging ? "border-steel-500 bg-steel-50 dark:bg-steel-950" : "border-gray-300 dark:border-slate-700"}`}
      >
        <UploadCloud size={28} className="text-steel-600" />
        <span className="text-sm font-medium">Drop files or click to upload</span>
        <span className="text-xs muted">CSV · PDF · SVG · MD · EML · PNG</span>
        <input
          type="file"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </label>

      {items.length > 0 && (
        <div className="mt-6 space-y-2">
          {items.map((it) => (
            <div key={it.id} className="surface flex items-center gap-3 rounded-lg px-3 py-2 text-sm">
              <StatusIcon status={it.status} />
              <span className="flex-1 truncate">{it.name}</span>
              <span className="text-xs muted capitalize">{it.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusIcon({ status }) {
  if (status === "uploading")
    return <Loader2 size={16} className="animate-spin text-steel-600" />;
  if (status === "accepted")
    return <CheckCircle2 size={16} className="text-emerald-600" />;
  return <span className="h-4 w-4 rounded-full bg-red-500" />;
}
