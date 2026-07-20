import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';
import { createCopilotSocket, startListening, speak } from '../../lib/copilot';
import Markdown from 'react-markdown';
import { Mic, MicOff, AlertTriangle, CheckCircle, Activity, Pause, Play, RefreshCw, Send, Headphones } from 'lucide-react';

export default function FieldCopilot() {
  const { session } = useAuth();
  const [sessionId, setSessionId] = useState(null);
  const [copilotState, setCopilotState] = useState(null);
  
  // Work Order to start (hardcoded for demo)
  const [workOrderId, setWorkOrderId] = useState('WO-2993');

  const [ws, setWs] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [responses, setResponses] = useState([]);
  
  const [isSpeaking, setIsSpeaking] = useState(false);

  // Initialize session
  const startSession = async () => {
    try {
      const res = await api.post('/agents/copilot/session', {
        worker_id: session?.user?.id || 'demo',
        work_order_id: workOrderId
      });
      setSessionId(res.session_id);
      setCopilotState(res);
      setResponses([{
        type: 'system',
        text: `Started session for ${workOrderId}. Loaded ${res.steps?.length || 0} steps.`
      }]);
    } catch (err) {
      console.error('Failed to start session:', err);
      alert('Failed to start session. See console.');
    }
  };

  // Setup WebSocket when we have a session
  useEffect(() => {
    if (!sessionId) return;
    
    const socket = createCopilotSocket(
      sessionId,
      session?.access_token,
      (data) => {
        // Handle incoming response
        setResponses(prev => [...prev, {
          type: 'agent',
          data: data
        }]);
        
        // Update local state if step changed
        if (data.step_index) {
          setCopilotState(prev => ({
            ...prev,
            current_step_index: data.step_index - 1
          }));
        }

        // Read aloud
        if (data.spoken_text) {
          setIsSpeaking(true);
          speak(data.spoken_text, () => setIsSpeaking(false));
        }
      },
      () => setIsConnected(false)
    );
    
    setWs(socket);
    setIsConnected(true);
    
    return () => {
      socket.close();
    };
  }, [sessionId, session]);


  // Handle Push-To-Talk
  const toggleListening = () => {
    if (isListening) {
      // Stop is handled by the startListening return or auto-timeout
      setIsListening(false);
    } else {
      setIsListening(true);
      setTranscript('');
      
      startListening(
        (text) => {
          setTranscript(text);
          setIsListening(false);
          
          if (text.trim() && ws) {
            setResponses(prev => [...prev, { type: 'user', text }]);
            ws.send(text);
          }
        },
        () => setIsListening(false)
      );
    }
  };


  if (!sessionId) {
    return (
      <div className="max-w-md mx-auto mt-20 p-6 bg-slate-800 rounded-xl border border-slate-700">
        <div className="flex items-center gap-3 mb-6 text-emerald-400">
          <Headphones size={32} />
          <h2 className="text-2xl font-semibold text-white">Field Copilot</h2>
        </div>
        <p className="text-slate-400 mb-6">
          Hands-free voice execution for field procedures. Starts a new tracking session and loads SOPs into cache.
        </p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Work Order ID</label>
            <input 
              type="text" 
              value={workOrderId} 
              onChange={(e) => setWorkOrderId(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-emerald-500"
            />
          </div>
          <button 
            onClick={startSession}
            className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-3 rounded-lg transition-colors"
          >
            <Play size={20} />
            Start Execution Session
          </button>
        </div>
      </div>
    );
  }

  // Active session view (Rugged / High Contrast for field use)
  const currentStepNum = (copilotState?.current_step_index || 0) + 1;
  const totalSteps = copilotState?.steps?.length || 0;
  const currentStepText = copilotState?.steps?.[copilotState?.current_step_index] || 'No steps available';
  
  // Find last agent response to see if there's a warning
  const lastAgentResponse = [...responses].reverse().find(r => r.type === 'agent');
  const isWarning = lastAgentResponse?.data?.spoken_text?.startsWith('WARNING:');

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-5xl mx-auto">
      
      {/* Header bar */}
      <div className="flex items-center justify-between p-4 bg-slate-800 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <Headphones className="text-emerald-400" />
          <h2 className="text-lg font-semibold text-white">
            Copilot • {workOrderId}
          </h2>
          {isConnected ? (
            <span className="flex items-center gap-1 text-xs text-emerald-400 bg-emerald-900/30 px-2 py-1 rounded-full border border-emerald-800">
              <Activity size={12} /> Live
            </span>
          ) : (
            <span className="text-xs text-rose-400 bg-rose-900/30 px-2 py-1 rounded-full border border-rose-800">
              Offline
            </span>
          )}
        </div>
        <div className="text-sm font-medium text-slate-400">
          Step {currentStepNum} of {totalSteps}
        </div>
      </div>

      {/* Warning Banner */}
      {isWarning && (
        <div className="bg-rose-500/10 border-b border-rose-500/20 p-4 flex items-start gap-3 animate-pulse">
          <AlertTriangle className="text-rose-500 shrink-0 mt-0.5" />
          <div className="text-rose-400 font-medium">
            SAFETY WARNING ACTIVE
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        
        {/* Current Step Giant Card */}
        <div className="bg-slate-800 rounded-2xl p-6 border border-slate-700 shadow-xl">
          <div className="text-xs font-bold tracking-wider text-slate-500 uppercase mb-3">
            Current Step
          </div>
          <div className="text-2xl text-white font-medium leading-relaxed">
            {currentStepText}
          </div>
        </div>

        {/* Conversation Log */}
        <div className="space-y-4 pb-32">
          {responses.map((msg, i) => (
            <div key={i} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl p-4 ${
                msg.type === 'user' 
                  ? 'bg-emerald-600 text-white rounded-br-none' 
                  : msg.type === 'system'
                    ? 'bg-slate-800 text-slate-400 border border-slate-700'
                    : 'bg-slate-700 text-slate-200 rounded-bl-none border border-slate-600'
              }`}>
                {msg.type === 'user' ? (
                  <div className="text-lg">{msg.text}</div>
                ) : msg.type === 'system' ? (
                  <div className="text-sm">{msg.text}</div>
                ) : (
                  <div>
                    {msg.data.intent_detected === 'LOG_OBSERVATION' && (
                      <div className="flex items-center gap-2 text-xs font-bold text-emerald-400 mb-2 uppercase tracking-wide">
                        <CheckCircle size={14} /> Logged to Graph
                      </div>
                    )}
                    <div className="prose prose-invert prose-emerald max-w-none">
                      <Markdown>{msg.data.display_text}</Markdown>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          
          {/* Live Transcript Preview */}
          {transcript && (
            <div className="flex justify-end opacity-70">
              <div className="bg-emerald-600/50 text-white rounded-2xl rounded-br-none p-4 text-lg">
                {transcript}...
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Giant PTT Button Area */}
      <div className="p-6 bg-slate-900 border-t border-slate-800">
        <button
          onMouseDown={toggleListening}
          onMouseUp={toggleListening}
          onTouchStart={(e) => { e.preventDefault(); toggleListening(); }}
          onTouchEnd={(e) => { e.preventDefault(); toggleListening(); }}
          className={`w-full h-32 rounded-3xl flex flex-col items-center justify-center gap-3 transition-all duration-200 ${
            isListening 
              ? 'bg-emerald-500 scale-[0.98] shadow-inner shadow-emerald-700' 
              : 'bg-slate-800 hover:bg-slate-700 border-2 border-slate-700 shadow-xl'
          }`}
        >
          {isListening ? (
            <>
              <div className="relative">
                <Mic size={48} className="text-white" />
                <span className="absolute inline-flex h-full w-full rounded-full bg-white opacity-40 animate-ping inset-0"></span>
              </div>
              <span className="text-white font-medium text-xl">Listening... (Release to send)</span>
            </>
          ) : (
            <>
              <Mic size={48} className={isConnected ? "text-emerald-400" : "text-slate-500"} />
              <span className="text-slate-300 font-medium text-xl">
                {isConnected ? 'Press and Hold to Speak' : 'Connecting...'}
              </span>
            </>
          )}
        </button>
        <div className="text-center mt-4 text-slate-500 text-sm">
          Try saying: "Next step", "Repeat", "What is the pressure limit?", "Note: valve is leaking"
        </div>
      </div>

    </div>
  );
}
