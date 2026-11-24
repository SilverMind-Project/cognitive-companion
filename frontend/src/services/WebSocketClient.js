/**
 * WebSocket client for real-time audio and push notifications (`/ws/audio`).
 *
 * The socket carries resident prompts and opens microphones, so it authenticates:
 * the API key goes in the `Sec-WebSocket-Protocol` header (a browser cannot set
 * other headers on a WebSocket, and a key in the URL would land in access logs).
 * A screen registered as a companion surface names itself in the URL so the
 * server sends it the deliveries for its room.
 */

import { wsUrl } from "@/services/apiOrigin";
import { getApiKey } from "@/services/http";

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
const SURFACE_HARDWARE_COMMAND_TYPE = "surface_hardware_command";
const SURFACE_ATTENTION_STATE_TYPE = "surface_attention_state";

export class WebSocketClient {
  /**
   * @param {string} baseUrl The socket URL without the surface query.
   * @param {{ keyProvider?: () => string }} [options]
   */
  constructor(baseUrl, { keyProvider = getApiKey } = {}) {
    this.baseUrl = baseUrl;
    this.surfaceId = "";
    this.platform = "";
    this._keyProvider = keyProvider;
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
      onSurfaceHardwareCommand: [],
    };
  }

  /** The URL for the current surface context. */
  get url() {
    const params = new URLSearchParams();
    if (this.surfaceId) params.set("surface_id", this.surfaceId);
    if (this.platform) params.set("platform", this.platform);
    const query = params.toString();
    return query ? `${this.baseUrl}?${query}` : this.baseUrl;
  }

  /**
   * Name the companion surface this screen is (empty for none) and its platform.
   * An open socket reconnects so the server routes this room's deliveries to it.
   */
  setSurfaceContext({ surfaceId = "", platform = "" } = {}) {
    const nextSurface = surfaceId?.trim() || "";
    const nextPlatform = platform || "";
    if (nextSurface === this.surfaceId && nextPlatform === this.platform) return;
    this.surfaceId = nextSurface;
    this.platform = nextPlatform;
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) {
      // Swap the socket without letting the old one's close start a reconnect loop.
      const previous = this.socket;
      previous.onclose = null;
      previous.close();
      this.socket = null;
      this.connect();
    }
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

    const key = this._keyProvider();
    try {
      this.socket = new WebSocket(this.url, key ? [key] : undefined);
    } catch (err) {
      // A key that is not a valid subprotocol token (RFC 7230: no spaces, commas,
      // slashes, or "=") throws here. Retrying cannot fix it, and throwing would
      // abort the page's start-up, so report it and stay disconnected.
      console.error("Companion socket could not be opened:", err);
      this.socket = null;
      this._notify("onDisconnect");
      return;
    }
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
        } else if (data.type === SURFACE_HARDWARE_COMMAND_TYPE) {
          this._notify("onSurfaceHardwareCommand", data);
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

  /**
   * Whether someone is facing this screen, from the native shell's on-device face
   * detection. Only presence and head angles: an image never leaves the device.
   */
  sendSurfaceAttentionState({ facePresent, headYawDeg = null, headPitchDeg = null }) {
    this._sendJson({
      type: SURFACE_ATTENTION_STATE_TYPE,
      face_present: Boolean(facePresent),
      head_yaw_deg: headYawDeg,
      head_pitch_deg: headPitchDeg,
      timestamp: new Date().toISOString(),
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

// Default instance: the companion socket on the API origin.
export const wsClient = new WebSocketClient(wsUrl("/ws/audio"));
