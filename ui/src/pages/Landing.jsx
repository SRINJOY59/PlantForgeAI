import { Link } from "react-router-dom";
import {
  Activity, ArrowRight, Boxes, FileSearch, GitBranch, ShieldCheck, Zap, Leaf,
} from "lucide-react";

const features = [
  { icon: FileSearch, color: "#2563eb", bg: "#dbeafe", title: "Ask anything, cited",
    body: "Work orders, P&IDs, SOPs, manuals, emails and photos become one queryable brain. Every answer carries its source." },
  { icon: GitBranch, color: "#7c3aed", bg: "#ede9fe", title: "Reasoning you can see",
    body: "PathRAG traverses the plant's real topology to answer causal questions — and shows the chain it followed." },
  { icon: Activity, color: "#dc2626", bg: "#fee2e2", title: "It warns you first",
    body: "Agents watch every new failure, connect it to sibling equipment, and push a grounded recommendation before you ask." },
  { icon: ShieldCheck, color: "#16a34a", bg: "#dcfce7", title: "Trust by design",
    body: "Document facts, agent inferences and human corrections are kept distinct. Nothing enters the brain unverified." },
  { icon: Boxes, color: "#d97706", bg: "#fef3c7", title: "Connect your systems",
    body: "Point a connector at your CMMS, historian or shared drive. The brain stays current on its own." },
  { icon: Zap, color: "#0284c7", bg: "#e0f2fe", title: "Answers before you ask",
    body: "When a failure is logged, the answer is pre-computed. By the time you open the app, it's already waiting." },
];

const stats = [
  { value: "35%",   label: "of engineers' time lost hunting for information" },
  { value: "18–22%", label: "of unplanned downtime from fragmented knowledge" },
  { value: "25%",   label: "of experienced engineers retiring within a decade" },
  { value: "7–12",  label: "disconnected document systems per plant" },
];

export default function Landing() {
  return (
    <div className="min-h-full overflow-y-auto" style={{ background: "var(--bg-surface)" }}>
      {/* Header */}
      <header
        className="sticky top-0 z-20 mx-auto flex max-w-7xl items-center justify-between px-6 py-4"
        style={{ background: "rgba(255,255,255,0.92)", backdropFilter: "blur(8px)", borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="grid h-9 w-9 place-items-center rounded-xl"
            style={{ background: "var(--blue)", boxShadow: "0 2px 8px rgba(37,99,235,0.3)" }}
          >
            <Leaf size={17} className="text-white" />
          </div>
          <span
            className="text-lg font-bold"
            style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--text)" }}
          >
            PlantMind
          </span>
        </div>
        <nav className="flex items-center gap-2">
          <Link to="/login" className="btn-ghost text-sm">Sign in</Link>
          <Link to="/app" className="btn-primary text-sm px-5">
            Launch app <ArrowRight size={14} />
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-5xl px-6 pt-20 pb-16 text-center">
        <div
          className="mb-5 inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-xs font-medium"
          style={{ background: "#eff6ff", borderColor: "#bfdbfe", color: "#1d4ed8" }}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#16a34a" }} />
          Industrial Knowledge Intelligence Platform
        </div>

        <h1
          className="text-balance text-5xl font-bold leading-tight tracking-tight sm:text-6xl"
          style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "#0f172a" }}
        >
          Every asset in your plant,{" "}
          <span className="gradient-text">given a memory.</span>
        </h1>

        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed" style={{ color: "var(--muted)" }}>
          PlantMind unifies the documents scattered across your plant into one knowledge graph —
          then answers operational questions with citations, warns you before failures repeat,
          and proves your compliance.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Link to="/app" className="btn-primary text-base px-6 py-3">
            Open the brain <ArrowRight size={16} />
          </Link>
          <Link to="/signup" className="btn-outline text-base px-6 py-3">
            Create account
          </Link>
        </div>

        {/* Tech tags */}
        <div className="mt-10 flex flex-wrap items-center justify-center gap-2">
          {["PathRAG", "Neo4j Graph", "Celery Workers", "SSE Streaming", "P&ID VLM", "Entity Resolution"].map((t) => (
            <span
              key={t}
              className="rounded-full px-3 py-1 text-xs font-medium"
              style={{ background: "var(--bg-subtle)", color: "var(--text-md)", border: "1px solid var(--border)" }}
            >
              {t}
            </span>
          ))}
        </div>
      </section>

      {/* Feature cards */}
      <section className="mx-auto max-w-6xl px-6 pb-20">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.title}
              className="group rounded-2xl p-6 transition-all duration-200 cursor-default"
              style={{
                background: "var(--bg-panel)",
                border: "1px solid var(--border)",
                boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.boxShadow = `0 8px 24px rgba(0,0,0,0.08)`;
                e.currentTarget.style.borderColor = "#bfdbfe";
                e.currentTarget.style.transform = "translateY(-2px)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.boxShadow = "0 1px 3px rgba(0,0,0,0.05)";
                e.currentTarget.style.borderColor = "var(--border)";
                e.currentTarget.style.transform = "translateY(0)";
              }}
            >
              <div
                className="mb-4 grid h-11 w-11 place-items-center rounded-xl"
                style={{ background: f.bg }}
              >
                <f.icon size={20} style={{ color: f.color }} />
              </div>
              <h3
                className="font-semibold mb-2"
                style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--text)" }}
              >
                {f.title}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                {f.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Stats */}
      <section
        className="py-16"
        style={{ background: "#eff6ff", borderTop: "1px solid #bfdbfe", borderBottom: "1px solid #bfdbfe" }}
      >
        <div className="mx-auto grid max-w-5xl grid-cols-2 gap-8 px-6 text-center sm:grid-cols-4">
          {stats.map(({ value, label }) => (
            <div key={label}>
              <div
                className="text-3xl font-bold mb-2"
                style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--blue)" }}
              >
                {value}
              </div>
              <div className="text-xs leading-relaxed" style={{ color: "var(--text-md)" }}>{label}</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="mx-auto max-w-7xl px-6 py-8">
        <div className="flex items-center justify-between">
          <span className="text-sm" style={{ color: "var(--muted-lt)" }}>
            PlantMind — built for industrial engineering.
          </span>
          <span className="text-xs font-mono" style={{ color: "var(--border-md)" }}>v2.0 · PathRAG</span>
        </div>
      </footer>
    </div>
  );
}
