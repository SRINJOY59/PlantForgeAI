import React, { useState, useEffect } from "react";
import { Settings, Save, AlertCircle, RefreshCw, ClipboardList, Check } from "lucide-react";
import { getEnvelopes, updateLimit, getLimitsAudit } from "../../../lib/api";

export default function LimitsPanel({ onLimitsUpdated }) {
  const [limits, setLimits] = useState({});
  const [audit, setAudit] = useState([]);
  const [editingTag, setEditingTag] = useState(null);
  const [editValues, setEditValues] = useState({ ll: "", l: "", h: "", hh: "", setpoint: "" });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [successTag, setSuccessTag] = useState(null);

  const fetchLimitsAndAudit = async () => {
    try {
      setLoading(true);
      const envData = await getEnvelopes();
      setLimits(envData);
      
      const auditData = await getLimitsAudit();
      setAudit(auditData);
      
      setError(null);
    } catch (e) {
      setError("Failed to fetch limits or audit trail.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLimitsAndAudit();
  }, []);

  const handleEditStart = (tagId, values) => {
    setEditingTag(tagId);
    setEditValues({
      ll: values.ll !== undefined ? values.ll : "",
      l: values.l !== undefined ? values.l : "",
      h: values.h !== undefined ? values.h : "",
      hh: values.hh !== undefined ? values.hh : "",
      setpoint: values.setpoint !== undefined ? values.setpoint : "",
    });
    setError(null);
  };

  const handleSave = async (tagId) => {
    // Parse values
    const ll = editValues.ll !== "" ? parseFloat(editValues.ll) : null;
    const l = editValues.l !== "" ? parseFloat(editValues.l) : null;
    const h = editValues.h !== "" ? parseFloat(editValues.h) : null;
    const hh = editValues.hh !== "" ? parseFloat(editValues.hh) : null;
    const sp = editValues.setpoint !== "" ? parseFloat(editValues.setpoint) : null;

    // Validate ll < l < h < hh
    const vals = [ll, l, h, hh].filter(v => v !== null);
    for (let i = 0; i < vals.length - 1; i++) {
      if (vals[i] >= vals[i + 1]) {
        setError("Invalid limit order: ll < l < h < hh must hold.");
        return;
      }
    }

    // Validate l < setpoint < h
    if (sp !== null) {
      if (l !== null && sp <= l) {
        setError(`Setpoint (${sp}) must be greater than Low limit (${l}).`);
        return;
      }
      if (h !== null && sp >= h) {
        setError(`Setpoint (${sp}) must be less than High limit (${h}).`);
        return;
      }
    }

    try {
      setLoading(true);
      await updateLimit(tagId, { ll, l, h, hh, setpoint: sp });
      setEditingTag(null);
      setSuccessTag(tagId);
      setTimeout(() => setSuccessTag(null), 3000);
      
      // Refresh limits list & audit
      await fetchLimitsAndAudit();
      
      if (onLimitsUpdated) {
        onLimitsUpdated();
      }
    } catch (e) {
      setError(e.message || "Failed to update limit configuration.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="rounded-xl p-4 shadow-sm space-y-4"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between border-b pb-2" style={{ borderColor: "var(--border)" }}>
        <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: "var(--text-md)" }}>
          <Settings size={16} className="text-blue-500" />
          Operating Limits & Setpoint Config (ISA-18.2)
        </h3>
        <button
          onClick={fetchLimitsAndAudit}
          className="p-1 rounded hover:bg-slate-100 transition-colors"
          title="Refresh Config"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg p-2.5 text-xs bg-rose-50 border border-rose-200 text-rose-800">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {/* Limits Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b" style={{ borderColor: "var(--border)", color: "var(--muted)" }}>
              <th className="py-2 font-semibold">Tag ID</th>
              <th className="py-2 font-semibold text-center text-rose-700">LL (Crit)</th>
              <th className="py-2 font-semibold text-center text-amber-600">L (Warn)</th>
              <th className="py-2 font-semibold text-center text-blue-600">Setpoint</th>
              <th className="py-2 font-semibold text-center text-amber-600">H (Warn)</th>
              <th className="py-2 font-semibold text-center text-rose-700">HH (Crit)</th>
              <th className="py-2 font-semibold text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(limits).map(([tagId, val]) => {
              const isEditing = editingTag === tagId;
              const hasSetpoint = val.setpoint !== undefined;

              return (
                <tr key={tagId} className="border-b hover:bg-slate-50/40" style={{ borderColor: "var(--border)" }}>
                  <td className="py-2 font-medium" style={{ color: "var(--text-md)" }}>
                    <div>{tagId}</div>
                    <div className="text-[9px] text-slate-400 font-normal">{val.unit || ""}</div>
                  </td>
                  
                  {/* LL (Low Low) */}
                  <td className="py-2 text-center">
                    {isEditing ? (
                      <input
                        type="number"
                        step="any"
                        value={editValues.ll}
                        onChange={(e) => setEditValues({ ...editValues, ll: e.target.value })}
                        className="w-16 rounded border bg-white p-1 text-center text-xs"
                        style={{ borderColor: "var(--border)" }}
                      />
                    ) : (
                      <span className="font-semibold text-rose-700">{val.ll !== undefined ? val.ll : "—"}</span>
                    )}
                  </td>

                  {/* L (Low) */}
                  <td className="py-2 text-center">
                    {isEditing ? (
                      <input
                        type="number"
                        step="any"
                        value={editValues.l}
                        onChange={(e) => setEditValues({ ...editValues, l: e.target.value })}
                        className="w-16 rounded border bg-white p-1 text-center text-xs"
                        style={{ borderColor: "var(--border)" }}
                      />
                    ) : (
                      <span className="font-semibold text-amber-600">{val.l !== undefined ? val.l : "—"}</span>
                    )}
                  </td>

                  {/* Setpoint */}
                  <td className="py-2 text-center">
                    {isEditing ? (
                      hasSetpoint ? (
                        <input
                          type="number"
                          step="any"
                          value={editValues.setpoint}
                          onChange={(e) => setEditValues({ ...editValues, setpoint: e.target.value })}
                          className="w-16 rounded border bg-white p-1 text-center text-xs font-semibold text-blue-700"
                          style={{ borderColor: "var(--border)" }}
                        />
                      ) : (
                        <span className="text-slate-300">—</span>
                      )
                    ) : (
                      <span className="font-bold text-blue-600">{val.setpoint !== undefined ? val.setpoint : "—"}</span>
                    )}
                  </td>

                  {/* H (High) */}
                  <td className="py-2 text-center">
                    {isEditing ? (
                      <input
                        type="number"
                        step="any"
                        value={editValues.h}
                        onChange={(e) => setEditValues({ ...editValues, h: e.target.value })}
                        className="w-16 rounded border bg-white p-1 text-center text-xs"
                        style={{ borderColor: "var(--border)" }}
                      />
                    ) : (
                      <span className="font-semibold text-amber-600">{val.h !== undefined ? val.h : "—"}</span>
                    )}
                  </td>

                  {/* HH (High High) */}
                  <td className="py-2 text-center">
                    {isEditing ? (
                      <input
                        type="number"
                        step="any"
                        value={editValues.hh}
                        onChange={(e) => setEditValues({ ...editValues, hh: e.target.value })}
                        className="w-16 rounded border bg-white p-1 text-center text-xs"
                        style={{ borderColor: "var(--border)" }}
                      />
                    ) : (
                      <span className="font-semibold text-rose-700">{val.hh !== undefined ? val.hh : "—"}</span>
                    )}
                  </td>

                  {/* Actions */}
                  <td className="py-2 text-right">
                    {isEditing ? (
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => handleSave(tagId)}
                          className="flex items-center gap-1 rounded bg-blue-600 px-2 py-1 text-[10px] font-bold text-white hover:bg-blue-700"
                        >
                          <Save size={10} />
                          Save
                        </button>
                        <button
                          onClick={() => setEditingTag(null)}
                          className="rounded bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-600 hover:bg-slate-200"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="flex justify-end items-center gap-1">
                        {successTag === tagId && (
                          <span className="flex items-center gap-0.5 text-[9px] font-bold text-emerald-600 mr-2">
                            <Check size={10} /> Saved
                          </span>
                        )}
                        <button
                          onClick={() => handleEditStart(tagId, val)}
                          className="rounded bg-slate-50 border px-2 py-1 text-[10px] font-bold text-slate-700 hover:bg-slate-100 transition-colors"
                          style={{ borderColor: "var(--border)" }}
                        >
                          Configure
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Audit Log */}
      <div className="border-t pt-3" style={{ borderColor: "var(--border)" }}>
        <h4 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1 mb-2">
          <ClipboardList size={12} />
          Change Log Audit Trail
        </h4>
        <div className="max-h-28 overflow-y-auto space-y-1.5 pr-1">
          {audit.length === 0 ? (
            <div className="text-[10px] text-slate-400 italic">No limit modifications registered.</div>
          ) : (
            audit.map((entry, idx) => (
              <div
                key={idx}
                className="text-[10px] flex items-start justify-between rounded p-1.5"
                style={{ background: "rgba(248,250,252,0.6)", border: "1px solid var(--border)" }}
              >
                <div>
                  <span className="font-semibold text-slate-700">{entry.tag_id}</span>
                  {" modified by "}
                  <span className="font-semibold text-slate-600">{entry.user}</span>
                  <div className="text-[9px] text-slate-400 mt-0.5 font-sans">
                    {Object.entries(entry.changes).map(([field, delta]) => (
                      <span key={field} className="mr-3 inline-block">
                        {field}: <span className="line-through text-slate-400">{delta.old !== null ? delta.old : "—"}</span>
                        {" → "}
                        <span className="font-semibold text-slate-700">{delta.new}</span>
                      </span>
                    ))}
                  </div>
                </div>
                <span className="text-[9px] text-slate-400 font-mono">
                  {new Date(entry.timestamp * 1000).toLocaleTimeString()}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
