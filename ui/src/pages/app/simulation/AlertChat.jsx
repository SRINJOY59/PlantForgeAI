import React, { useState, useRef, useEffect } from "react";
import { Send, X, Loader2, Sparkles, FileText, ArrowRight } from "lucide-react";
import { askStream, toHistory } from "../../../lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function AlertChat({ alert, rca, onClose, onOpenDoc }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  // Seed the chat with an initial system greeting grounded in the alert context
  useEffect(() => {
    if (!alert) return;
    
    const tag = alert.tag_id || alert.equipment;
    const rule = alert.rule || alert.title;
    const val = alert.value !== undefined ? alert.value : "";
    const threshold = alert.threshold !== undefined ? alert.threshold : "";
    
    let welcomeText = `Hello! I am the PlantForge Reliability Assistant. I've been seeded with the context of the **${tag}** limit breach (${rule}). `;
    
    if (rca && rca.summary) {
      welcomeText += `My initial root-cause analysis is: \n\n${rca.summary}\n\nAsk me anything about how this failure propagates, related operating procedures, or corrective actions.`;
    } else {
      welcomeText += `Ask me anything about how to investigate this incident or check governing procedures.`;
    }

    setMessages([
      {
        sender: "agent",
        text: welcomeText,
        citations: rca?.citations || []
      }
    ]);
  }, [alert, rca]);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, busy]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || busy) return;

    const userQuestion = input.trim();
    setInput("");
    setBusy(true);

    // Append user message
    setMessages((prev) => [...prev, { sender: "user", text: userQuestion }]);

    // Build alert context for the backend
    const tag = alert.tag_id || alert.equipment;
    const rule = alert.rule || alert.title;
    const val = alert.value !== undefined ? alert.value : "";
    const threshold = alert.threshold !== undefined ? alert.threshold : "";
    const rcaText = rca?.summary || "";
    
    const alertContext = `
Equipment/Tag: ${tag}
Breach Rule: ${rule}
Current Value: ${val}
Limit Threshold: ${threshold}
Initial Agent RCA: ${rcaText}
    `.trim();

    // Prepare message history turn structure for retrieval service
    const historyTurns = [];
    // Skip the initial welcome message, take user/agent turns in pairs
    for (let i = 1; i < messages.length; i++) {
      const msg = messages[i];
      if (msg.sender === "user") {
        historyTurns.push({ question: msg.text, answer: null });
      } else if (msg.sender === "agent" && historyTurns.length > 0) {
        historyTurns[historyTurns.length - 1].answer = { text: msg.text };
      }
    }

    // Append placeholder for agent's streaming response
    const agentMsgIndex = messages.length + 1;
    setMessages((prev) => [...prev, { sender: "agent", text: "", citations: [] }]);

    try {
      let currentText = "";
      const done = await askStream(
        userQuestion,
        (token) => {
          currentText += token;
          setMessages((prev) => {
            const next = [...prev];
            if (next[agentMsgIndex]) {
              next[agentMsgIndex] = { ...next[agentMsgIndex], text: currentText };
            }
            return next;
          });
        },
        historyTurns,
        alertContext
      );

      // Once done, set final answer details (including citations)
      setMessages((prev) => {
        const next = [...prev];
        if (next[agentMsgIndex]) {
          next[agentMsgIndex] = {
            ...next[agentMsgIndex],
            text: done?.text || currentText,
            citations: done?.citations || []
          };
        }
        return next;
      });
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        if (next[agentMsgIndex]) {
          next[agentMsgIndex] = {
            ...next[agentMsgIndex],
            text: "⚠️ Failed to reach the gateway assistant. Please verify that the services are online.",
            error: true
          };
        }
        return next;
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex flex-col rounded-xl overflow-hidden shadow-lg border"
      style={{
        background: "var(--bg-panel)",
        borderColor: "var(--border)",
        height: "450px"
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ borderColor: "var(--border)", background: "rgba(248,250,252,0.5)" }}
      >
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-blue-500 animate-pulse" />
          <span className="text-xs font-semibold text-slate-800">
            Alert Scope Agent Chat: <span className="font-mono">{alert.tag_id || alert.equipment}</span>
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded-full hover:bg-slate-100"
        >
          <X size={14} />
        </button>
      </div>

      {/* Messages Scroll Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4"
        style={{ background: "rgba(241,245,249,0.15)" }}
      >
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-3 py-2 text-xs border ${
                msg.sender === "user"
                  ? "bg-blue-600 text-white border-blue-700 rounded-tr-none"
                  : "bg-white text-slate-800 border-slate-200 rounded-tl-none shadow-sm"
              }`}
            >
              <div className="prose prose-sm max-w-none break-words">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text || "Thinking..."}</ReactMarkdown>
              </div>

              {/* Citations block */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 border-t pt-2 border-slate-100 flex flex-wrap gap-1">
                  {msg.citations.map((c, cIdx) => (
                    <button
                      key={cIdx}
                      type="button"
                      onClick={() => onOpenDoc?.(c.doc_id, c.filename || c.doc_id)}
                      className="flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[9px] bg-slate-50 border hover:bg-slate-100 text-blue-700 border-blue-200 transition-colors"
                    >
                      <FileText size={9} />
                      {c.filename || c.doc_id}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="flex items-center gap-2 py-1">
            <Loader2 size={12} className="animate-spin text-blue-500" />
            <span className="text-[10px] text-slate-400 font-medium">Agent is thinking...</span>
          </div>
        )}
      </div>

      {/* Composer Input Form */}
      <form
        onSubmit={handleSend}
        className="flex items-center gap-2 p-3 border-t bg-white"
        style={{ borderColor: "var(--border)" }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
          placeholder="Ask about this failure's root cause, history, or SOPs..."
          className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-blue-500 transition-colors"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-slate-100 disabled:text-slate-300 text-white rounded-lg p-1.5 transition-colors"
        >
          <Send size={12} />
        </button>
      </form>
    </div>
  );
}
