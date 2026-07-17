import { useState } from "react";
import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { historyEnabled } from "../../lib/history";

export default function HistoryPanel({ conversations, activeId, onSelect,
                                       onNew, onDelete, loading }) {
  return (
    <aside className="hidden lg:flex w-56 shrink-0 flex-col"
      style={{ borderRight: "1px solid var(--border)", background: "var(--bg-surface)" }}>
      <div className="flex-shrink-0 p-3">
        <button onClick={onNew}
          className="btn-primary w-full justify-center py-2 text-xs">
          <Plus size={13} /> New chat
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        <h3 className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--muted)" }}>
          History
        </h3>

        {!historyEnabled ? (
          <p className="px-2 py-4 text-[11px] leading-relaxed" style={{ color: "var(--muted-lt)" }}>
            Demo mode — conversations aren't saved. Configure Supabase to keep history.
          </p>
        ) : loading ? (
          <p className="px-2 py-4 text-[11px]" style={{ color: "var(--muted-lt)" }}>Loading…</p>
        ) : !conversations.length ? (
          <p className="px-2 py-4 text-[11px] leading-relaxed" style={{ color: "var(--muted-lt)" }}>
            Your past questions will appear here.
          </p>
        ) : (
          <div className="space-y-0.5">
            {conversations.map((c) => (
              <Row key={c.id} conversation={c} active={c.id === activeId}
                onSelect={() => onSelect(c.id)} onDelete={() => onDelete(c.id)} />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

function Row({ conversation, active, onSelect, onDelete }) {
  const [hover, setHover] = useState(false);
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="group flex items-center gap-1.5 rounded-lg px-2 py-2 transition-colors duration-150"
      style={{ background: active ? "#eff6ff" : hover ? "var(--bg-subtle)" : "transparent" }}
    >
      <button onClick={onSelect} className="flex min-w-0 flex-1 items-center gap-2 text-left">
        <MessageSquare size={12} className="flex-shrink-0"
          style={{ color: active ? "var(--blue)" : "var(--muted-lt)" }} />
        <div className="min-w-0">
          <p className="truncate text-[11px] font-medium"
            style={{ color: active ? "var(--blue)" : "var(--text-md)" }}>
            {conversation.title}
          </p>
          <p className="text-[9px]" style={{ color: "var(--muted-lt)" }}>
            {relativeTime(conversation.updated_at)}
          </p>
        </div>
      </button>
      {hover && (
        <button onClick={onDelete} className="btn-ghost flex-shrink-0 px-1 py-1"
          title="Delete conversation">
          <Trash2 size={11} style={{ color: "var(--danger)" }} />
        </button>
      )}
    </div>
  );
}

function relativeTime(iso) {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}
