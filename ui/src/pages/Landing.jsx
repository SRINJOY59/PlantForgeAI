import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity, ArrowRight, Boxes, GitBranch, ShieldCheck,
  Search, Clock, FileCheck, ChevronRight, FileSearch, Zap
} from "lucide-react";
import Logo from "../components/Logo";

const features = [
  { 
    id: "f1",
    colSpan: "md:col-span-2 lg:col-span-2", 
    icon: FileSearch, color: "#2563eb", bg: "#eff6ff", 
    title: "Ask anything, cited",
    body: "Work orders, P&IDs, SOPs, manuals, emails and photos become one queryable brain. Every answer carries its source." 
  },
  { 
    id: "f2",
    colSpan: "md:col-span-1 lg:col-span-1", 
    icon: GitBranch, color: "#7c3aed", bg: "#f5f3ff", 
    title: "Reasoning you can see",
    body: "PathRAG traverses the plant's real topology to answer causal questions." 
  },
  { 
    id: "f3",
    colSpan: "md:col-span-1 lg:col-span-1", 
    icon: Activity, color: "#dc2626", bg: "#fef2f2", 
    title: "It warns you first",
    body: "Agents watch every new failure and push a grounded recommendation before you ask." 
  },
  { 
    id: "f4",
    colSpan: "md:col-span-1 lg:col-span-1", 
    icon: ShieldCheck, color: "#16a34a", bg: "#f0fdf4", 
    title: "Trust by design",
    body: "Document facts, agent inferences and human corrections are kept distinct." 
  },
  { 
    id: "f5",
    colSpan: "md:col-span-2 lg:col-span-1", 
    icon: Zap, color: "#0284c7", bg: "#f0f9ff", 
    title: "Answers before you ask",
    body: "When a failure is logged, the answer is pre-computed. By the time you open the app, it's already waiting." 
  },
  { 
    id: "f6",
    colSpan: "md:col-span-2 lg:col-span-2", 
    icon: Boxes, color: "#d97706", bg: "#fffbeb", 
    title: "Connect your systems",
    body: "Point a connector at your CMMS, historian or shared drive. The brain stays current on its own without manual syncs." 
  },
  { 
    id: "f7",
    colSpan: "md:col-span-1 lg:col-span-1", 
    icon: Clock, color: "#be185d", bg: "#fdf2f8", 
    title: "Always in sync",
    body: "Real-time updates ensure the knowledge graph never goes stale." 
  },
];

const useCases = [
  {
    id: "rca",
    title: "Root Cause Analysis",
    icon: Search,
    color: "#2563eb",
    bg: "#eff6ff",
    description: "Trace a pump failure back to an unmentioned design flaw in P&IDs across decades, resolving issues in minutes instead of weeks.",
  },
  {
    id: "handover",
    title: "Shift Handovers",
    icon: Clock,
    color: "#0891b2",
    bg: "#ecfeff",
    description: "Instantly generate context-rich shift summaries. Ensure no critical warnings or unread updates fall through the cracks.",
  },
  {
    id: "audit",
    title: "Compliance & Audits",
    icon: FileCheck,
    color: "#059669",
    bg: "#ecfdf5",
    description: "Prove your compliance automatically by citing exactly which SOPs were followed during any maintenance operation.",
  }
];

const stats = [
  { value: "35%", label: "of engineers' time lost hunting for information" },
  { value: "18–22%", label: "of unplanned downtime from fragmented knowledge" },
  { value: "25%", label: "of experienced engineers retiring within a decade" },
  { value: "7–12", label: "disconnected document systems per plant" },
];

export default function Landing() {
  const [activeUseCase, setActiveUseCase] = useState(useCases[0].id);

  return (
    <div className="min-h-screen bg-slate-50 overflow-x-hidden selection:bg-brand-500/30 font-sans">
      
      {/* Absolute Mesh Gradient Background */}
      <div className="absolute top-0 left-0 right-0 h-[800px] w-full overflow-hidden pointer-events-none -z-10">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[70%] rounded-full bg-brand-300/30 blur-[120px]" />
        <div className="absolute top-[20%] right-[-10%] w-[40%] h-[60%] rounded-full bg-indigo-300/20 blur-[100px]" />
        <div className="absolute bottom-[-20%] left-[20%] w-[60%] h-[50%] rounded-full bg-violet-300/20 blur-[140px]" />
        {/* Subtle grid pattern overlay */}
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-[0.03] mix-blend-overlay" />
      </div>

      {/* Modern Header */}
      <header className="sticky top-4 z-50 mx-auto max-w-6xl px-6 transition-all">
        <div className="flex h-14 items-center justify-between rounded-full border border-white/40 bg-white/60 px-6 shadow-[0_8px_32px_rgba(0,0,0,0.04)] backdrop-blur-xl">
          <div className="flex items-center gap-2.5">
            <Logo size={30} />
            <span className="text-[17px] font-bold tracking-tight text-slate-900" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
              PlantForge<span className="text-brand-600">.ai</span>
            </span>
          </div>
          <nav className="flex items-center gap-2 sm:gap-4">
            <Link to="/login" className="text-sm font-semibold text-slate-600 transition-colors hover:text-slate-900">
              Sign in
            </Link>
            <Link to="/app" className="flex items-center gap-1.5 rounded-full bg-slate-900 px-4 py-1.5 text-sm font-semibold text-white transition-all hover:bg-slate-800 hover:shadow-lg hover:-translate-y-0.5">
              Launch <ArrowRight size={14} />
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative mx-auto max-w-5xl px-6 pt-20 pb-12 text-center sm:pt-28 sm:pb-16">
        <div className="mb-6 inline-flex cursor-default items-center gap-2 rounded-full border border-brand-200/50 bg-white/50 px-4 py-1.5 text-xs font-bold uppercase tracking-widest text-brand-700 shadow-sm backdrop-blur-md transition-transform hover:scale-105">
          <span className="h-1.5 w-1.5 rounded-full bg-brand-600 animate-pulse" />
          Industrial Intelligence V2
        </div>

        <h1 className="text-balance text-4xl font-extrabold leading-[1.1] tracking-tighter text-slate-900 sm:text-5xl lg:text-[3.5rem] mb-6" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
          Every asset in your plant,<br className="hidden sm:block" />
          <span className="bg-gradient-to-r from-brand-600 via-indigo-500 to-violet-600 bg-clip-text text-transparent"> given a memory.</span>
        </h1>

        <p className="mx-auto max-w-2xl text-lg leading-relaxed text-slate-600 font-medium">
          PlantForge.ai unifies the documents scattered across your plant into one knowledge graph —
          answering questions with precise citations and warning you before failures repeat.
        </p>

        <div className="mt-12 flex flex-col items-center justify-center gap-4 sm:flex-row">
          <Link to="/app" className="group flex items-center justify-center gap-2 rounded-full bg-brand-600 px-8 py-4 text-base font-bold text-white shadow-[0_4px_14px_rgba(122,84,160,0.39)] transition-all hover:bg-brand-700 hover:shadow-[0_6px_20px_rgba(122,84,160,0.23)] hover:-translate-y-1 w-full sm:w-auto">
            Open the brain <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
          </Link>
          <Link to="/signup" className="flex items-center justify-center rounded-full border-2 border-slate-200 bg-white px-8 py-4 text-base font-bold text-slate-900 transition-all hover:border-slate-300 hover:bg-slate-50 hover:-translate-y-1 w-full sm:w-auto">
            Create account
          </Link>
        </div>

        <div className="mt-16 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 opacity-60 grayscale transition-all hover:grayscale-0 hover:opacity-100">
          <p className="w-full text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">Powered by</p>
          {["PathRAG", "Neo4j Graph", "Celery", "SSE Streaming"].map((t) => (
            <span key={t} className="text-sm font-bold text-slate-700">
              {t}
            </span>
          ))}
        </div>
      </section>

      {/* Bento Grid Features */}
      <section className="mx-auto max-w-6xl px-6 pb-32">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
            Built for Industrial Scale.
          </h2>
          <p className="mt-3 text-base text-slate-600 font-medium max-w-2xl mx-auto">
            A meticulously designed platform that understands your plant's topology and grounds every answer in verifiable reality.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.id}
              className={`group relative flex flex-col justify-between overflow-hidden rounded-[32px] bg-white p-8 transition-all duration-500 hover:-translate-y-1 hover:shadow-[0_20px_40px_-10px_rgba(0,0,0,0.08)] ${f.colSpan}`}
              style={{
                border: "1px solid rgba(226, 232, 240, 0.8)",
                boxShadow: "0 4px 12px rgba(0,0,0,0.02)",
              }}
            >
              <div className="relative z-10 flex flex-col h-full">
                <div
                  className="mb-8 grid h-14 w-14 place-items-center rounded-2xl shadow-sm transition-transform duration-500 group-hover:scale-110 group-hover:rotate-3"
                  style={{ background: f.bg }}
                >
                  <f.icon size={26} style={{ color: f.color }} />
                </div>
                <div className="mt-auto">
                  <h3 className="mb-2 text-xl font-bold tracking-tight text-slate-900" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                    {f.title}
                  </h3>
                  <p className="text-sm font-medium leading-relaxed text-slate-500">
                    {f.body}
                  </p>
                </div>
              </div>
              
              {/* Subtle hover gradient overlay */}
              <div className="absolute inset-0 z-0 bg-gradient-to-br from-white via-white to-slate-50/50 opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
            </div>
          ))}
        </div>
      </section>

      {/* Dynamic Use Cases Section */}
      <section className="relative overflow-hidden bg-slate-900 py-32 text-white">
        {/* Dark Mode Mesh Gradient */}
        <div className="absolute inset-0 pointer-events-none opacity-40">
          <div className="absolute top-0 right-1/4 h-[500px] w-[500px] rounded-full bg-brand-600/30 blur-[120px] mix-blend-screen" />
          <div className="absolute bottom-0 left-1/4 h-[600px] w-[600px] rounded-full bg-purple-600/20 blur-[150px] mix-blend-screen" />
        </div>

        <div className="relative z-10 mx-auto max-w-6xl px-6">
          <div className="mb-16 text-center">
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
              Use Cases that Drive ROI
            </h2>
            <p className="mt-4 text-lg text-slate-400 font-medium max-w-2xl mx-auto">
              Empowering every role in the plant to make faster, safer, and more informed decisions.
            </p>
          </div>
          
          <div className="flex flex-col gap-12 lg:flex-row lg:items-center">
            {/* Left side: Interactive Selectors */}
            <div className="flex w-full flex-col gap-4 lg:w-5/12">
              {useCases.map((uc) => (
                <button
                  key={uc.id}
                  onClick={() => setActiveUseCase(uc.id)}
                  className={`group relative flex items-center justify-between rounded-3xl p-6 text-left transition-all duration-300 ${
                    activeUseCase === uc.id 
                      ? 'bg-white/10 shadow-lg ring-1 ring-white/20' 
                      : 'bg-transparent hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center gap-5">
                     <div className={`grid h-12 w-12 place-items-center rounded-2xl transition-all duration-300 ${
                       activeUseCase === uc.id ? 'scale-110 shadow-lg' : 'opacity-60 grayscale group-hover:grayscale-0 group-hover:opacity-100'
                     }`} style={{ background: uc.color }}>
                        <uc.icon size={24} className="text-white" />
                     </div>
                     <span className={`text-lg font-bold tracking-tight transition-colors ${
                       activeUseCase === uc.id ? 'text-white' : 'text-slate-400 group-hover:text-slate-200'
                     }`} style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                       {uc.title}
                     </span>
                  </div>
                  <ChevronRight size={24} className={`transition-all duration-300 ${
                    activeUseCase === uc.id ? 'text-white translate-x-2' : 'text-slate-600 opacity-0 group-hover:opacity-100'
                  }`} />
                </button>
              ))}
            </div>
            
            {/* Right side: Active Content Display */}
            <div className="relative h-[400px] w-full lg:w-7/12 perspective-1000">
               {useCases.map((uc) => (
                 <div 
                    key={`content-${uc.id}`}
                    className={`absolute inset-0 flex flex-col justify-center rounded-[40px] bg-gradient-to-br from-white/10 to-white/5 border border-white/10 p-12 backdrop-blur-xl transition-all duration-700 ease-[cubic-bezier(0.23,1,0.32,1)] ${
                      activeUseCase === uc.id 
                        ? 'opacity-100 translate-y-0 rotate-y-0 scale-100 z-10' 
                        : 'opacity-0 translate-y-12 rotate-y-12 scale-95 pointer-events-none'
                    }`}
                    style={{
                      boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255,255,255,0.1)"
                    }}
                 >
                    <div className="mb-6 grid h-14 w-14 place-items-center rounded-2xl bg-white shadow-xl">
                      <uc.icon size={28} style={{ color: uc.color }} />
                    </div>
                    <h3 className="mb-4 text-2xl font-extrabold tracking-tight text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                      {uc.title}
                    </h3>
                    <p className="mb-8 text-lg font-medium leading-relaxed text-slate-300">
                      {uc.description}
                    </p>
                    <div>
                      <Link to="/app" className="group/link inline-flex items-center gap-2 rounded-full bg-white/10 px-6 py-3 text-sm font-bold text-white transition-all hover:bg-white hover:text-slate-900">
                        See it in action <ArrowRight size={16} className="transition-transform group-hover/link:translate-x-1" />
                      </Link>
                    </div>
                 </div>
               ))}
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="border-t border-slate-200 bg-white py-24">
        <div className="mx-auto grid max-w-6xl grid-cols-1 gap-12 px-6 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map(({ value, label }) => (
            <div key={label} className="group text-center">
              <div
                className="mb-3 text-4xl font-black tracking-tighter text-brand-600 transition-transform duration-500 group-hover:scale-110 group-hover:text-brand-700"
                style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
              >
                {value}
              </div>
              <div className="mx-auto max-w-[200px] text-sm font-semibold leading-relaxed text-slate-500">
                {label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-slate-50 py-12">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-6 px-6 sm:flex-row">
          <div className="flex items-center gap-3 text-sm font-bold text-slate-400">
            <Logo size={22} className="opacity-60" />
            PlantForge.ai — Built for industrial engineering.
          </div>
          <div className="rounded-full bg-white px-4 py-1.5 text-xs font-bold tracking-widest text-slate-400 shadow-sm ring-1 ring-slate-200">
            V2.0 PATHRAG
          </div>
        </div>
      </footer>
    </div>
  );
}
