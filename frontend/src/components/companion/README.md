# Companion Kiosk

Standard PWAs cannot start always-on microphone capture from a cold page load.
Browsers require a user gesture before opening or resuming the microphone and
AudioContext. Kiosk mode therefore means one caregiver or resident tap, then a
warm WebSocket, retained mic permission for that page session, backend-triggered
mic re-arm, screen wake lock, and surface heartbeat.

A genuine no-tap always-on experience requires a native app with foreground
service microphone access. That is outside the guided companion M11 scope.
