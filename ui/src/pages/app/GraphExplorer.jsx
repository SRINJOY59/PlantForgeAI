import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { getGraph } from "../../lib/api";
import { Box, FileText, Zap, GitBranch, Circle, Search, ZoomIn, ZoomOut, Maximize2, RefreshCw, X, ChevronRight } from "lucide-react";

const NODE_TYPES = {
  Equipment:  { color: "#2563eb", bg: "#dbeafe", Icon: Box,      label: "Equipment"  },
  Document:   { color: "#d97706", bg: "#fef3c7", Icon: FileText, label: "Document"   },
  Event:      { color: "#dc2626", bg: "#fee2e2", Icon: Zap,      label: "Event"      },
  Unit:       { color: "#7c3aed", bg: "#ede9fe", Icon: GitBranch,label: "Unit"       },
  Instrument: { color: "#059669", bg: "#d1fae5", Icon: Circle,   label: "Instrument" },
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

  const visibleNodes = allNodes.filter(n => filterType === "all" || n.type === filterType);
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
      .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", "#cbd5e1");

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
      .attr("stroke", "#e2e8f0").attr("stroke-width", 1.5).attr("marker-end", "url(#arrow)");

    // Edge labels
    const linkLabel = g.append("g").selectAll("text").data(edges).join("text")
      .attr("text-anchor", "middle").attr("font-size", "7px").attr("fill", "#94a3b8")
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

    const r = d => d.type === "Unit" ? 26 : 17;

    // Outer circle (fill)
    node.append("circle").attr("r", r)
      .attr("fill", d => NODE_TYPES[d.type]?.bg ?? "#f1f5f9")
      .attr("stroke", d => NODE_TYPES[d.type]?.color ?? "#94a3b8")
      .attr("stroke-width", 1.5);

    // Label
    node.append("text").attr("text-anchor", "middle").attr("dy", d => r(d) + 14)
      .attr("font-size", d => d.type === "Unit" ? "10px" : "9px")
      .attr("font-weight", d => d.type === "Unit" ? "700" : "500")
      .attr("fill", d => NODE_TYPES[d.type]?.color ?? "#64748b")
      .attr("pointer-events", "none").text(d => d.label);

    // Fail count badge
    node.filter(d => d.failCount > 0).append("circle")
      .attr("cx", 13).attr("cy", -13).attr("r", 7)
      .attr("fill", "#dc2626").attr("stroke", "#fff").attr("stroke-width", 1.5);
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
  }, [filterType]);

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
          style={{ background: "#fff", borderBottom: "1px solid var(--border)", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--muted)" }} />
            <input className="input h-8 pl-8 pr-3 text-xs" style={{ width: "180px" }}
              placeholder="Search nodes…" value={search} onChange={e => setSearch(e.target.value)} />
          </div>

          <div className="flex items-center gap-1">
            <button onClick={() => setFilterType("all")} className="rounded-lg px-2.5 py-1 text-xs font-medium transition-all"
              style={filterType === "all" ? { background: "#dbeafe", color: "var(--blue)" } : { color: "var(--muted)" }}>
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
        <div className="relative flex-1 overflow-hidden" style={{ background: "#f8fafc" }}>
          {loading && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3"
              style={{ background: "rgba(248,250,252,0.85)", backdropFilter: "blur(4px)" }}>
              <div className="grid h-14 w-14 place-items-center rounded-2xl"
                style={{ background: "#dbeafe", border: "1px solid #bfdbfe" }}>
                <RefreshCw size={24} className="animate-spin" style={{ color: "var(--blue)" }} />
              </div>
              <p className="text-xs" style={{ color: "var(--muted)" }}>Laying out knowledge graph…</p>
            </div>
          )}
          <svg ref={svgRef} className="h-full w-full" style={{ background: "transparent" }} />

          {/* Legend */}
          <div className="absolute bottom-4 left-4 rounded-xl p-3"
            style={{ background: "#fff", border: "1px solid var(--border)", boxShadow: "0 2px 8px rgba(0,0,0,0.06)" }}>
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
              style={{ background: "#fff", border: "1px solid var(--border)", color: "var(--muted-lt)" }}>
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
          background: "#fff",
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
              style={{ background: "#f8fafc", border: "1px solid var(--border)", color: "var(--muted)" }}>
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
                        style={{ background: "#f8fafc", border: "1px solid var(--border)" }}
                        onMouseEnter={el => { el.currentTarget.style.background = "#eff6ff"; el.currentTarget.style.borderColor = "#bfdbfe"; }}
                        onMouseLeave={el => { el.currentTarget.style.background = "#f8fafc"; el.currentTarget.style.borderColor = "var(--border)"; }}
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
      style={{ background: "#f8fafc", border: "1px solid var(--border)" }}>
      <span className="text-[11px]" style={{ color: "var(--muted)" }}>{label}</span>
      <span className="text-[11px] font-semibold" style={{ color: "var(--text)", ...valueStyle }}>{value}</span>
    </div>
  );
}
