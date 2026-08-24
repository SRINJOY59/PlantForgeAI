import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { getGraph } from "../../lib/api";
import { Box, FileText, AlertTriangle, Wrench, Gauge, ListChecks, ShieldCheck, User, Search, ZoomIn, ZoomOut, Maximize2, RefreshCw, X, ChevronRight } from "lucide-react";

// mirrors NodeType in plantmind_core.schemas - every label the graph can
// actually return. Anything missing here renders grey and unfilterable.
const NODE_TYPES = {
  Equipment:        { color: "#2563eb", bg: "#dbeafe", Icon: Box,           label: "Equipment"  },
  Instrument:       { color: "#059669", bg: "#d1fae5", Icon: Gauge,         label: "Instrument" },
  Document:         { color: "#d97706", bg: "#fef3c7", Icon: FileText,      label: "Document"   },
  WorkOrder:        { color: "#7c3aed", bg: "#ede9fe", Icon: Wrench,        label: "Work Order" },
  FailureMode:      { color: "#dc2626", bg: "#fee2e2", Icon: AlertTriangle, label: "Failure"    },
  Procedure:        { color: "#0891b2", bg: "#cffafe", Icon: ListChecks,    label: "Procedure"  },
  RegulationClause: { color: "#4f46e5", bg: "#e0e7ff", Icon: ShieldCheck,   label: "Regulation" },
  Person:           { color: "#db2777", bg: "#fce7f3", Icon: User,          label: "Person"     },
};

export default function GraphExplorer() {
  const svgRef = useRef(null);
  const zoomRef = useRef(null);
  const [selected, setSelected] = useState(null);
  const [filterType, setFilterType] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [allNodes, setAllNodes] = useState([]);
  const [allEdges, setAllEdges] = useState([]);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);

  useEffect(() => {
    getGraph().then(data => {
      const formattedNodes = data.nodes.map(n => ({
        id: n.id,
        label: n.surface || n.id,
        type: n.label,
        desc: n.props?.description || n.props?.summary || "",
        unit: n.props?.unit || "",
        failCount: n.props?.failCount || 0
      }));
      const formattedEdges = data.edges.map(e => ({
        source: e.src,
        target: e.dst,
        label: e.type
      }));
      setAllNodes(formattedNodes);
      setAllEdges(formattedEdges);
    }).catch(err => {
      console.error(err);
    });
  }, []);

  // The search box was bound to state that nothing ever read - typing filtered
  // precisely nothing. Matches on the label a person actually sees plus the
  // node type, so "pump", "P-101" and "equipment" all narrow the canvas.
  const needle = search.trim().toLowerCase();
  const visibleNodes = allNodes.filter(n => {
    if (filterType !== "all" && n.type !== filterType) return false;
    if (!needle) return true;
    return (n.label || "").toLowerCase().includes(needle)
        || (n.id || "").toLowerCase().includes(needle)
        || (n.type || "").toLowerCase().includes(needle);
  });
  const visibleIds = new Set(visibleNodes.map(n => n.id));
  const visibleEdges = allEdges.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target));

  useEffect(() => {
    if (!svgRef.current || allNodes.length === 0) return;
    const el = svgRef.current;
    const W = el.clientWidth, H = el.clientHeight;
    d3.select(el).selectAll("*").remove();

    const svg = d3.select(el).attr("width", W).attr("height", H);
    const defs = svg.append("defs");

    // Arrowhead
    defs.append("marker").attr("id", "arrow").attr("viewBox", "0 -5 10 10")
      .attr("refX", 24).attr("refY", 0).attr("markerWidth", 6).attr("markerHeight", 6).attr("orient", "auto")
      .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", "var(--border-md)");

    const g = svg.append("g");
    const zoom = d3.zoom().scaleExtent([0.2, 4]).on("zoom", e => g.attr("transform", e.transform));
    zoomRef.current = zoom;
    svg.call(zoom);
    svg.call(zoom.transform, d3.zoomIdentity.translate(W/2, H/2).scale(0.8));

    const nodes = visibleNodes.map(n => ({ ...n }));
    const edges = visibleEdges.map(e => ({ ...e }));
    setNodeCount(nodes.length); setEdgeCount(edges.length);

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(edges).id(d => d.id).distance(110).strength(0.5))
      .force("charge", d3.forceManyBody().strength(-380))
      .force("center", d3.forceCenter(0, 0))
      .force("collision", d3.forceCollide().radius(32));

    // Do NOT fast-forward synchronously, let it animate naturally
    // so the browser doesn't freeze and nodes don't explode to NaN.

    // Edges
    const link = g.append("g").selectAll("line").data(edges).join("line")
      .attr("stroke", "var(--border)").attr("stroke-width", 1.5).attr("marker-end", "url(#arrow)");

    // Edge labels
    const linkLabel = g.append("g").selectAll("text").data(edges).join("text")
      .attr("text-anchor", "middle").attr("font-size", "7px").attr("fill", "var(--muted-lt)")
      .attr("pointer-events", "none").text(d => d.label);

    // Node groups
    const node = g.append("g").selectAll("g").data(nodes).join("g")
      .attr("cursor", "pointer")
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag",  (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end",   (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
      )
      .on("click", (e, d) => { e.stopPropagation(); setSelected(allNodes.find(n => n.id === d.id)); })
      .on("mouseenter", function(e, d) {
        d3.select(this).select("circle:first-child").attr("stroke-width", 2.5);
      })
      .on("mouseleave", function(e, d) {
        d3.select(this).select("circle:first-child").attr("stroke-width", 1.5);
      });

    // equipment and instruments are the plant itself - draw them larger than
    // the paperwork hanging off them
    const PRIMARY = new Set(["Equipment", "Instrument"]);
    const r = d => PRIMARY.has(d.type) ? 22 : 15;

    // Outer circle (fill)
    node.append("circle").attr("r", r)
      .attr("fill", d => NODE_TYPES[d.type]?.bg ?? "var(--bg-subtle)")
      .attr("stroke", d => NODE_TYPES[d.type]?.color ?? "var(--muted-lt)")
      .attr("stroke-width", 1.5);

    // Label
    node.append("text").attr("text-anchor", "middle").attr("dy", d => r(d) + 14)
      .attr("font-size", d => PRIMARY.has(d.type) ? "10px" : "8px")
      .attr("font-weight", d => PRIMARY.has(d.type) ? "700" : "500")
      .attr("fill", d => NODE_TYPES[d.type]?.color ?? "var(--muted)")
      .attr("pointer-events", "none").text(d => d.label)
      .attr("opacity", d => PRIMARY.has(d.type) ? 1 : 0.75);

    // Fail count badge
    node.filter(d => d.failCount > 0).append("circle")
      .attr("cx", 13).attr("cy", -13).attr("r", 7)
      .attr("fill", "#dc2626").attr("stroke", "var(--bg-panel)").attr("stroke-width", 1.5);
    node.filter(d => d.failCount > 0).append("text")
      .attr("x", 13).attr("y", -13).attr("text-anchor", "middle").attr("dominant-baseline", "middle")
      .attr("font-size", "7px").attr("font-weight", "bold").attr("fill", "white")
      .attr("pointer-events", "none").text(d => d.failCount);

    svg.on("click", () => setSelected(null));

    const updatePositions = () => {
      link.attr("x1", d => d.source.x || 0).attr("y1", d => d.source.y || 0)
          .attr("x2", d => d.target.x || 0).attr("y2", d => d.target.y || 0);
      linkLabel.attr("x", d => ((d.source.x || 0) + (d.target.x || 0))/2).attr("y", d => ((d.source.y || 0) + (d.target.y || 0))/2);
      node.attr("transform", d => `translate(${d.x || 0},${d.y || 0})`);
    };

    setLoading(false);
    sim.on("tick", updatePositions);
    return () => sim.stop();
    // allNodes/allEdges land asynchronously - without them here the effect
    // bails once on mount and never redraws when the data arrives
    // `search` belongs here too: it now narrows visibleNodes, so leaving it
    // out meant the filter was correct and the canvas never redrew to show it.
  }, [filterType, search, allNodes, allEdges]);

  function zoomIn()    { d3.select(svgRef.current).transition().call(zoomRef.current.scaleBy, 1.4); }
  function zoomOut()   { d3.select(svgRef.current).transition().call(zoomRef.current.scaleBy, 0.7); }
  function resetZoom() {
    const el = svgRef.current;
    d3.select(el).transition().call(zoomRef.current.transform,
      d3.zoomIdentity.translate(el.clientWidth/2, el.clientHeight/2).scale(0.8));
  }

  const selCfg = selected ? NODE_TYPES[selected.type] : null;
  const connEdges = selected ? allEdges.filter(e => e.source === selected.id || e.target === selected.id) : [];

  return (
    <div className="flex h-full">
      {/* Graph area */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* Toolbar */}
        <div className="flex flex-shrink-0 items-center gap-3 px-4 py-3"
          style={{ background: "var(--bg-panel)", borderBottom: "1px solid var(--border)", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--muted)" }} />
            <input className="input h-8 pl-8 pr-3 text-xs" style={{ width: "180px" }}
              placeholder="Search nodes…" value={search} onChange={e => setSearch(e.target.value)} />
          </div>

          <div className="flex items-center gap-1">
            <button onClick={() => setFilterType("all")} className="rounded-lg px-2.5 py-1 text-xs font-medium transition-all"
              style={filterType === "all" ? { background: "var(--brand-light)", color: "var(--blue)" } : { color: "var(--muted)" }}>
              All
            </button>
            {Object.entries(NODE_TYPES).map(([type, cfg]) => (
              <button key={type} onClick={() => setFilterType(type === filterType ? "all" : type)}
                className="rounded-lg px-2.5 py-1 text-xs font-medium transition-all"
                style={filterType === type ? { background: cfg.bg, color: cfg.color } : { color: "var(--muted)" }}>
                {cfg.label}
              </button>
            ))}
          </div>

          <div className="flex-1" />
          <span className="text-xs" style={{ color: "var(--muted-lt)" }}>{nodeCount} nodes · {edgeCount} edges</span>
          <div className="flex items-center gap-1">
            <button onClick={zoomIn}   className="btn-ghost px-2 py-1.5"><ZoomIn   size={14} /></button>
            <button onClick={zoomOut}  className="btn-ghost px-2 py-1.5"><ZoomOut  size={14} /></button>
            <button onClick={resetZoom} className="btn-ghost px-2 py-1.5"><Maximize2 size={14} /></button>
          </div>
        </div>

        {/* SVG canvas */}
        <div className="relative flex-1 overflow-hidden" style={{ background: "var(--bg-surface)" }}>
          {loading && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3"
              style={{ background: "rgba(248,250,252,0.85)", backdropFilter: "blur(4px)" }}>
              <div className="grid h-14 w-14 place-items-center rounded-2xl"
                style={{ background: "var(--brand-light)", border: "1px solid var(--brand-mid)" }}>
                <RefreshCw size={24} className="animate-spin" style={{ color: "var(--blue)" }} />
              </div>
              <p className="text-xs" style={{ color: "var(--muted)" }}>Laying out knowledge graph…</p>
            </div>
          )}
          <svg ref={svgRef} className="h-full w-full" style={{ background: "transparent" }} />

          {/* Legend */}
          <div className="absolute bottom-4 left-4 rounded-xl p-3"
            style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", boxShadow: "0 2px 8px rgba(0,0,0,0.06)" }}>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
              Legend
            </p>
            {Object.entries(NODE_TYPES).map(([type, cfg]) => (
              <div key={type} className="flex items-center gap-2 mb-1">
                <span className="h-2.5 w-2.5 rounded-full flex-shrink-0" style={{ background: cfg.color }} />
                <span className="text-[10px]" style={{ color: "var(--muted)" }}>{cfg.label}</span>
              </div>
            ))}
            <div className="mt-1.5 pt-1.5" style={{ borderTop: "1px solid var(--border)" }}>
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#dc2626" }} />
                <span className="text-[10px]" style={{ color: "var(--muted)" }}>Failure count</span>
              </div>
            </div>
          </div>

          {!selected && !loading && (
            <div className="absolute bottom-4 right-4 rounded-xl px-3 py-2 text-xs"
              style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", color: "var(--muted-lt)" }}>
              Click node to inspect · Drag to move · Scroll to zoom
            </div>
          )}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-shrink-0 overflow-y-auto transition-all duration-300"
        style={{
          width: selected ? "270px" : "0px",
          minWidth: selected ? "270px" : "0px",
          background: "var(--bg-panel)",
          borderLeft: "1px solid var(--border)",
          boxShadow: selected ? "-2px 0 8px rgba(0,0,0,0.04)" : "none",
        }}>
        {selected && selCfg && (
          <div className="p-4 animate-slide-up">
            <div className="mb-4 flex items-center justify-between">
              <span className="badge" style={{ background: selCfg.bg, color: selCfg.color }}>
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: selCfg.color }} />
                {selected.type}
              </span>
              <button onClick={() => setSelected(null)} className="btn-ghost px-1.5 py-1"><X size={14} /></button>
            </div>

            <div className="mb-4 flex items-center gap-3">
              <div className="grid h-11 w-11 flex-shrink-0 place-items-center rounded-xl"
                style={{ background: selCfg.bg, border: `1px solid ${selCfg.color}30` }}>
                <selCfg.Icon size={20} style={{ color: selCfg.color }} />
              </div>
              <div>
                <h2 className="font-bold text-sm" style={{ color: "var(--text)" }}>{selected.label}</h2>
                <p className="text-[10px] font-mono mt-0.5" style={{ color: "var(--muted)" }}>{selected.id}</p>
              </div>
            </div>

            <div className="mb-4 rounded-xl p-3 text-xs leading-relaxed"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--muted)" }}>
              {selected.desc ?? "No description available."}
            </div>

            {selected.unit && <PropRow label="Unit" value={selected.unit} />}
            {selected.failCount != null && (
              <PropRow label="Failures" value={selected.failCount}
                valueStyle={{ color: selected.failCount > 0 ? "#dc2626" : "var(--success)" }} />
            )}

            {connEdges.length > 0 && (
              <div className="mt-4">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
                  Connections ({connEdges.length})
                </p>
                <div className="space-y-1.5">
                  {connEdges.slice(0, 8).map((e, i) => {
                    const isSource = e.source === selected.id;
                    const otherId = isSource ? e.target : e.source;
                    const other = allNodes.find(n => n.id === otherId);
                    const otherCfg = other ? NODE_TYPES[other.type] : null;
                    return (
                      <button key={i} onClick={() => setSelected(other)}
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-left transition-all"
                        style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
                        onMouseEnter={el => { el.currentTarget.style.background = "var(--brand-light)"; el.currentTarget.style.borderColor = "var(--brand-mid)"; }}
                        onMouseLeave={el => { el.currentTarget.style.background = "var(--bg-surface)"; el.currentTarget.style.borderColor = "var(--border)"; }}
                      >
                        <span className="h-2 w-2 flex-shrink-0 rounded-full" style={{ background: otherCfg?.color ?? "#94a3b8" }} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[11px] font-medium" style={{ color: "var(--text-md)" }}>
                            {other?.label ?? otherId}
                          </p>
                          <p className="text-[10px]" style={{ color: "var(--muted)" }}>
                            {isSource ? "→" : "←"} {e.label}
                          </p>
                        </div>
                        <ChevronRight size={11} style={{ color: "var(--muted-lt)" }} />
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function PropRow({ label, value, valueStyle }) {
  return (
    <div className="flex items-center justify-between rounded-lg px-3 py-2 mb-1.5"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
      <span className="text-[11px]" style={{ color: "var(--muted)" }}>{label}</span>
      <span className="text-[11px] font-semibold" style={{ color: "var(--text)", ...valueStyle }}>{value}</span>
    </div>
  );
}
