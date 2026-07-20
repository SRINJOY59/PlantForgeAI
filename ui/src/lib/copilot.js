/**
 * Field Copilot client-side library.
 * 
 * Wraps browser-native Web Speech API for transcription and TTS.
 * This keeps the backend lightweight and avoids sending audio over the wire.
 */

export function createCopilotSocket(sessionId, token, onMessage, onClose) {
  // Use ws:// or wss:// depending on protocol
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  // Use VITE_API_URL if available, otherwise assume same host but port 8000 (gateway)
  const host = import.meta.env.VITE_API_URL 
    ? new URL(import.meta.env.VITE_API_URL).host 
    : 'localhost:8000';
  
  const url = `${protocol}//${host}/ws/copilot/${sessionId}?token=${token || ''}`;
  const ws = new WebSocket(url);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error('Failed to parse copilot message:', e);
    }
  };

  ws.onclose = () => {
    if (onClose) onClose();
  };

  return {
    send: (text) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ text }));
      } else {
        console.warn('WebSocket not open. ReadyState:', ws.readyState);
      }
    },
    close: () => ws.close()
  };
}

export function startListening(onTranscript, onStop) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  
  if (!SpeechRecognition) {
    console.error('Speech recognition not supported in this browser.');
    alert('Speech recognition is not supported in this browser. Please use Chrome or Edge.');
    if (onStop) onStop();
    return null;
  }

  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    onTranscript(transcript);
  };

  recognition.onerror = (event) => {
    console.error('Speech recognition error:', event.error);
    if (onStop) onStop();
  };

  recognition.onend = () => {
    if (onStop) onStop();
  };

  try {
    recognition.start();
    return () => recognition.stop();
  } catch (e) {
    console.error('Failed to start recognition:', e);
    if (onStop) onStop();
    return null;
  }
}

export function speak(text, onEnd) {
  if (!window.speechSynthesis) {
    console.error('Speech synthesis not supported in this browser.');
    if (onEnd) onEnd();
    return;
  }

  // Cancel any ongoing speech
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-US';
  
  if (onEnd) {
    utterance.onend = onEnd;
    utterance.onerror = onEnd;
  }
  
  window.speechSynthesis.speak(utterance);
}
