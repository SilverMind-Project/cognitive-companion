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
    };
  }

  connect() {
    if (this.socket?.readyState === WebSocket.OPEN) return;

    // Reset reconnect budget so that an explicit connect() call (e.g. on
    // page load or after a deliberate disconnect) always re-enables the
    // automatic reconnection logic.
    this.maxReconnectAttempts = 10;
    this.attempts = 0;

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

  on(event, callback) {
    if (this.callbacks[event]) {
      this.callbacks[event].push(callback);
    }
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
    setTimeout(() => this.connect(), this.reconnectInterval * this.attempts);
  }
}

// Default instance - connects relative to current host
const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
export const wsClient = new WebSocketClient(`${wsProto}//${location.host}/ws/audio`);
