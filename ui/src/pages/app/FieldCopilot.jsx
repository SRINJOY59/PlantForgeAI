import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../auth/AuthProvider';
import { startCopilotSession } from '../../lib/api';
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
      const res = await startCopilotSession({
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
      <div className="card max-w-md mx-auto mt-20 p-6">
        <div className="flex items-center gap-3 mb-6" style={{ color: 'var(--blue)' }}>
          <Headphones size={32} />
          <h2 className="text-2xl font-semibold" style={{ color: 'var(--text)' }}>Field Copilot</h2>
        </div>
        <p className="mb-6" style={{ color: 'var(--muted)' }}>
          Hands-free voice execution for field procedures. Starts a new tracking session and loads SOPs into cache.
        </p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1" style={{ color: 'var(--text-md)' }}>Work Order ID</label>
            <input 
              type="text" 
              value={workOrderId} 
              onChange={(e) => setWorkOrderId(e.target.value)}
              className="input"
            />
          </div>
          <button 
            onClick={startSession}
            className="btn-primary w-full justify-center py-3 text-base"
          >
            <Play size={20} />
            Start Execution Session
          </button>
        </div>
      </div>
    );
  }

  // Active session view
  const currentStepNum = (copilotState?.current_step_index || 0) + 1;
  const totalSteps = copilotState?.steps?.length || 0;
  const currentStepText = copilotState?.steps?.[copilotState?.current_step_index] || 'No steps available';
  
  // Find last agent response to see if there's a warning
  const lastAgentResponse = [...responses].reverse().find(r => r.type === 'agent');
  const isWarning = lastAgentResponse?.data?.spoken_text?.startsWith('WARNING:');

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-5xl mx-auto">
      
      {/* Header bar */}
      <div className="flex items-center justify-between p-4 border-b" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-3">
          <Headphones style={{ color: 'var(--blue)' }} />
          <h2 className="text-lg font-semibold" style={{ color: 'var(--text)' }}>
            Copilot • {workOrderId}
          </h2>
          {isConnected ? (
            <span className="badge badge-green flex items-center gap-1">
              <Activity size={12} /> Live
            </span>
          ) : (
            <span className="badge badge-red">
              Offline
            </span>
          )}
        </div>
        <div className="text-sm font-medium" style={{ color: 'var(--muted)' }}>
          Step {currentStepNum} of {totalSteps}
        </div>
      </div>

      {/* Warning Banner */}
      {isWarning && (
        <div className="p-4 flex items-start gap-3 animate-pulse" style={{ background: 'var(--badge-red)', borderBottom: '1px solid var(--danger)' }}>
          <AlertTriangle size={20} style={{ color: 'var(--danger)' }} className="shrink-0 mt-0.5" />
          <div className="font-medium" style={{ color: 'var(--danger)' }}>
            SAFETY WARNING ACTIVE
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        
        {/* Current Step Card */}
        <div className="card p-6 shadow-md">
          <div className="text-xs font-bold tracking-wider uppercase mb-3" style={{ color: 'var(--muted)' }}>
            Current Step
          </div>
          <div className="text-2xl font-medium leading-relaxed" style={{ color: 'var(--text)' }}>
            {currentStepText}
          </div>
        </div>

        {/* Conversation Log */}
        <div className="space-y-4 pb-32">
          {responses.map((msg, i) => (
            <div key={i} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl p-4 ${msg.type === 'user' ? 'rounded-br-none' : 'rounded-bl-none border'}`}
                   style={{
                     background: msg.type === 'user' ? 'var(--blue)' : msg.type === 'system' ? 'var(--bg-subtle)' : 'var(--bg-panel)',
                     color: msg.type === 'user' ? '#fff' : 'var(--text)',
                     borderColor: msg.type === 'user' ? 'transparent' : 'var(--border)'
                   }}>
                {msg.type === 'user' ? (
                  <div className="text-lg">{msg.text}</div>
                ) : msg.type === 'system' ? (
                  <div className="text-sm" style={{ color: 'var(--muted)' }}>{msg.text}</div>
                ) : (
                  <div>
                    {msg.data.intent_detected === 'LOG_OBSERVATION' && (
                      <div className="flex items-center gap-2 text-xs font-bold mb-2 uppercase tracking-wide" style={{ color: 'var(--success)' }}>
                        <CheckCircle size={14} /> Logged to Graph
                      </div>
                    )}
                    <div className="prose prose-sm max-w-none dark:prose-invert">
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
              <div className="rounded-2xl rounded-br-none p-4 text-lg" style={{ background: 'var(--blue-mid)', color: '#fff' }}>
                {transcript}...
              </div>
            </div>
          )}
        </div>
      </div>

      {/* PTT Button Area */}
      <div className="p-6 border-t" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}>
        <button
          onMouseDown={toggleListening}
          onMouseUp={toggleListening}
          onTouchStart={(e) => { e.preventDefault(); toggleListening(); }}
          onTouchEnd={(e) => { e.preventDefault(); toggleListening(); }}
          className={`w-full h-32 rounded-3xl flex flex-col items-center justify-center gap-3 transition-all duration-200 border-2 shadow-sm ${
            isListening ? 'scale-[0.98]' : 'hover:opacity-90'
          }`}
          style={{
            background: isListening ? 'var(--blue)' : 'var(--bg-surface)',
            borderColor: isListening ? 'var(--blue-dark)' : 'var(--border-md)',
            boxShadow: isListening ? 'inset 0 4px 6px rgba(0,0,0,0.1)' : '0 4px 6px var(--shadow)'
          }}
        >
          {isListening ? (
            <>
              <div className="relative">
                <Mic size={48} color="#fff" />
                <span className="absolute inline-flex h-full w-full rounded-full bg-white opacity-40 animate-ping inset-0"></span>
              </div>
              <span className="font-medium text-xl text-white">Listening... (Release to send)</span>
            </>
          ) : (
            <>
              <Mic size={48} style={{ color: isConnected ? 'var(--blue)' : 'var(--muted)' }} />
              <span className="font-medium text-xl" style={{ color: 'var(--text)' }}>
                {isConnected ? 'Press and Hold to Speak' : 'Connecting...'}
              </span>
            </>
          )}
        </button>
        <div className="text-center mt-4 text-sm" style={{ color: 'var(--muted)' }}>
          Try saying: "Next step", "Repeat", "What is the pressure limit?", "Note: valve is leaking"
        </div>
      </div>

    </div>
  );
}
