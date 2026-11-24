/**
 * WebSocket client for real-time audio and push notifications.
 */

const NOTIFICATION_TYPES = new Set([
  "command",
  "emergency",
  "emergency_alert",
  "info",
  "reminder",
  "warning",
]);

const INTERACTIVE_PROMPT_TYPE = "interactive_prompt";
const INTERACTIVE_RESPONSE_TYPE = "interactive_response";
const ENABLE_MICROPHONE_TYPE = "enable_microphone";
const KNOWLEDGE_ANSWER_TYPE = "knowledge_answer";
const GUIDED_SESSION_STATE_TYPE = "guided_session_state";
const GUIDED_STEP_ACTION_TYPE = "guided_step_action";
const GUIDED_STEP_ACTION_RESULT_TYPE = "guided_step_action_result";

export class WebSocketClient {
  constructor(url) {
    this.url = url;
    this.socket = null;
    this.reconnectInterval = 2000;
    this.maxReconnectAttempts = 10;
    this.attempts = 0;

    // Announcement streaming state
    this._announcementStreaming = false;
    this._announcementSampleRate = 24000;

    this.callbacks = {
      onTranscript: [],
      onCommand: [],
      onConnect: [],
      onDisconnect: [],
      onAudioBlob: [],
      onStatus: [],
      onAnnouncement: [],
      onInteractivePrompt: [],
      onInteractiveResponse: [],
      onEnableMicrophone: [],
      onKnowledgeAnswer: [],
      onGuidedSessionState: [],
      onGuidedStepActionResult: [],
    };
  }

  connect({ resetAttempts = true } = {}) {
    if (this.socket?.readyState === WebSocket.OPEN) return;

    // Reset reconnect budget so that an explicit connect() call (e.g. on
    // page load or after a deliberate disconnect) always re-enables the
    // automatic reconnection logic.
    if (resetAttempts) {
      this.maxReconnectAttempts = 10;
      this.attempts = 0;
    }

    this.socket = new WebSocket(this.url);
    this.socket.binaryType = "arraybuffer";

    this.socket.onopen = () => {
      this.attempts = 0;
      this._notify("onConnect");
    };

    this.socket.onclose = () => {
      this._notify("onDisconnect");
      this._reconnect();
    };

    this.socket.onerror = (e) => {
      console.error("WebSocket error:", e);
    };

    this.socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        if (this._announcementStreaming) {
          // Route binary frames to announcement handler during TTS stream
          this._notify("onAnnouncement", {
            subtype: "pcm_chunk",
            data: event.data,
            sampleRate: this._announcementSampleRate,
          });
        } else {
          this._notify("onAudioBlob", event.data);
        }
        return;
      }

      try {
        const data = JSON.parse(event.data);
        if (data.type === "pwa_tts_announcement") {
          if (data.subtype === "stream_start") {
            this._announcementStreaming = true;
            this._announcementSampleRate = data.sample_rate || 24000;
          } else if (data.subtype === "stream_end") {
            this._announcementStreaming = false;
          }
          this._notify("onAnnouncement", data);
        } else if (data.type === "transcript") {
          this._notify("onTranscript", data);
        } else if (data.type === "status") {
          this._notify("onStatus", data);
        } else if (data.type === "error") {
          this._notify("onStatus", data);
        } else if (data.type === "tool_calls") {
          this._notify("onStatus", data);
        } else if (data.type === INTERACTIVE_PROMPT_TYPE) {
          this._notify("onInteractivePrompt", data);
        } else if (data.type === INTERACTIVE_RESPONSE_TYPE) {
          this._notify("onInteractiveResponse", data);
        } else if (data.type === ENABLE_MICROPHONE_TYPE) {
          this._notify("onEnableMicrophone", data);
        } else if (data.type === KNOWLEDGE_ANSWER_TYPE) {
          this._notify("onKnowledgeAnswer", data);
        } else if (data.type === GUIDED_SESSION_STATE_TYPE) {
          this._notify("onGuidedSessionState", data);
        } else if (data.type === GUIDED_STEP_ACTION_RESULT_TYPE) {
          this._notify("onGuidedStepActionResult", data);
        } else if (NOTIFICATION_TYPES.has(data.type)) {
          this._notify("onCommand", data);
        } else {
          this._notify("onStatus", data);
        }
      } catch {
        // ignore malformed messages
      }
    };
  }

  disconnect() {
    this.maxReconnectAttempts = 0;
    this.socket?.close();
  }

  sendAudio(buffer) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(buffer);
    }
  }

  sendEndOfTurn() {
    this._sendJson({ type: "end_of_turn" });
  }

  sendText(text) {
    this._sendJson({ type: "text", text });
  }

  sendInteractiveResponse(executionId, stepId, action) {
    this._sendJson({
      type: INTERACTIVE_RESPONSE_TYPE,
      execution_id: executionId,
      step_id: stepId,
      action: action,
      timestamp: new Date().toISOString(),
    });
  }

  /**
   * A tap on the guided-task widget. `stepOrd` is the step the screen showed;
   * the server ignores a "done" for any other step, so a screen that has not
   * caught up can never complete a step she has not seen.
   */
  sendGuidedStepAction(sessionId, action, stepOrd) {
    this._sendJson({
      type: GUIDED_STEP_ACTION_TYPE,
      session_id: sessionId,
      action,
      step_ord: stepOrd,
    });
  }

  /** True when a message can be sent right now. */
  get isOpen() {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  on(event, callback) {
    if (this.callbacks[event]) {
      this.callbacks[event].push(callback);
    }
  }

  off(event, callback) {
    if (!this.callbacks[event]) return;
    this.callbacks[event] = this.callbacks[event].filter((cb) => cb !== callback);
  }

  _sendJson(data) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(data));
    }
  }

  _notify(event, data) {
    for (const cb of this.callbacks[event] || []) {
      try {
        cb(data);
      } catch (e) {
        console.error(`Callback error for ${event}:`, e);
      }
    }
  }

  _reconnect() {
    if (this.attempts >= this.maxReconnectAttempts) return;
    this.attempts++;
    const delay = Math.min(this.reconnectInterval * 2 ** (this.attempts - 1), 30000);
    setTimeout(() => this.connect({ resetAttempts: false }), delay);
  }
}

// Default instance - connects relative to current host
const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
export const wsClient = new WebSocketClient(`${wsProto}//${location.host}/ws/audio`);
