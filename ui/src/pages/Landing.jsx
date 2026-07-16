import { Link } from "react-router-dom";
import {
  Activity, ArrowRight, Boxes, FileSearch, GitBranch, ShieldCheck, Zap,
} from "lucide-react";

const features = [
  {
    icon: FileSearch,
    title: "Ask anything, cited",
    body: "Work orders, P&IDs, SOPs, manuals, emails and photos become one queryable brain. Every answer carries its source.",
  },
  {
    icon: GitBranch,
    title: "Reasoning you can see",
    body: "PathRAG traverses the plant's real topology to answer causal questions — and shows the chain it followed.",
  },
  {
    icon: Activity,
    title: "It warns you first",
    body: "Agents watch every new failure, connect it to sibling equipment, and push a grounded recommendation before you ask.",
  },
  {
    icon: ShieldCheck,
    title: "Trust by design",
    body: "Document facts, agent inferences and human corrections are kept distinct. Nothing enters the brain unverified.",
  },
  {
    icon: Boxes,
    title: "Connect your systems",
    body: "Point a connector at your CMMS, historian or shared drive. The brain stays current on its own.",
  },
  {
    icon: Zap,
    title: "Answers before you ask",
    body: "When a failure is logged, the answer is pre-computed. By the time you open the app, it's already waiting.",
  },
];

export default function Landing() {
  return (
    <div className="min-h-full bg-white dark:bg-slate-950">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-steel-600 text-white">
            P
          </span>
          PlantMind
        </div>
        <nav className="flex items-center gap-2">
          <Link to="/login" className="btn-ghost">Sign in</Link>
          <Link to="/app" className="btn-primary">
            Launch app <ArrowRight size={16} />
          </Link>
        </nav>
      </header>

      <section className="mx-auto max-w-4xl px-6 pb-16 pt-16 text-center">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1 text-xs muted dark:border-slate-800">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Industrial Knowledge Intelligence
        </div>
        <h1 className="text-balance text-5xl font-bold tracking-tight sm:text-6xl">
          Every asset in your plant,
          <span className="text-steel-600"> given a memory.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg muted">
          PlantMind unifies the documents scattered across your plant into one
          knowledge graph — then answers operational questions with citations,
          warns you before failures repeat, and proves your compliance.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link to="/app" className="btn-primary text-base">
            Open the brain <ArrowRight size={18} />
          </Link>
          <Link to="/signup" className="btn-ghost text-base">
            Create account
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 pb-24">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div key={f.title} className="surface rounded-xl p-5">
              <f.icon className="text-steel-600" size={22} />
              <h3 className="mt-3 font-semibold">{f.title}</h3>
              <p className="mt-1.5 text-sm muted">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-gray-100 bg-gray-50 dark:border-slate-900 dark:bg-slate-950">
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-8 px-6 py-14 text-center sm:grid-cols-4">
          {[
            ["35%", "of engineers' time lost hunting for information"],
            ["18–22%", "of unplanned downtime from fragmented knowledge"],
            ["25%", "of experienced engineers retiring within a decade"],
            ["7–12", "disconnected document systems per plant"],
          ].map(([stat, label]) => (
            <div key={label}>
              <div className="text-3xl font-bold text-steel-600">{stat}</div>
              <div className="mt-1 text-xs muted">{label}</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="mx-auto max-w-6xl px-6 py-8 text-sm muted">
        PlantMind — built for core engineering firms.
      </footer>
    </div>
  );
}
