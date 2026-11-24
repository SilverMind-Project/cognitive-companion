# Cognitive Companion Android shell (tablet and Google TV / Android TV)

A Capacitor 8 shell around the companion page served by the household server, so
a companion tablet or TV can wake, speak, and listen when the server asks, with no
tap from the resident. One APK serves both form factors.

## Status

**Built and tested on the Windows build PC** (`scripts/ccwin`, see
`scripts/windows/README.md`): this Linux host is aarch64 and Google ships no
linux-arm64 build tools. The gate is `scripts/ccwin check`: `companion-core` tests,
Android lint with warnings as errors (reviewed exceptions in `app/lint.xml`), and the
debug APK. The instrumented tests (`app/src/androidTest/`) run live against the
household server on wiped tablet and Google TV emulators
(`scripts/ccwin test-instrumented tablet|tv`).

## Layout

| Path | Contents |
| --- | --- |
| `companion-core/` | Pure Kotlin/JVM decision logic: capture lease, volume floor, command parsing, attention change detection. A standalone Gradle build with JUnit 5 tests; needs only a JDK 21. |
| `app/src/main/java/com/silvermind/companion/` | `MainActivity` (zero-gesture WebView, capture grants for its own origin, device-owner kiosk), `CompanionHardwarePlugin` (the page's `CompanionHardware`), `CompanionForegroundService`, `FrontCameraAttentionAnalyzer` (CameraX + on-device ML Kit; no image leaves the device), boot and device-admin receivers. |
| `app/src/main/res/raw/gentle_chime.wav` | The attention chime (generated: two soft notes, slow attack). |

The Capacitor template's generated files (`capacitor.settings.gradle`,
`app/capacitor.build.gradle`, `capacitor-cordova-android-plugins/`) are rewritten by
`npx cap sync`; do not edit them.

## The contract with the page and the server

The server sends `surface_hardware_command` (`backend/schemas/companion_surface_ws.py`)
over `/ws/audio` to the one surface in the resident's room, never as a broadcast.
`frontend/src/composables/useNativeCompanionHardware.js` passes it to
`CompanionHardware.applyCommand`. Every capture carries a lease; the plugin closes
capture when it runs out unrenewed (and tells the page with `leaseExpired`), so a
lost release can never leave a microphone or camera open. The camera reports only
`facePresenceChanged` (`facePresent`, `yaw`, `pitch`).

## Building

From the repository root (the web build and `cap sync` run here, Gradle on the PC):

```bash
export CC_COMPANION_URL='https://nanai.khoofia.com/companion?kiosk=1'
scripts/ccwin sync && scripts/ccwin check
```

`CC_COMPANION_URL` must be HTTPS: microphone capture needs a secure origin. On the
home network that is `https://nanai.khoofia.com/companion?kiosk=1`, served by the
cluster ingress with a Let's Encrypt certificate (`kubernetes/edge/` at the workspace
root); the page calls the API on `https://api.nanai.khoofia.com`.

Core logic only, on any JDK 21 host (including this one):

```bash
cd frontend/android/companion-core && ../gradlew -p . test
```

## Provisioning a dedicated device (kiosk)

On a factory-reset device with no accounts:

```bash
adb install app-debug.apk
adb shell dpm set-device-owner com.silvermind.companion/.CompanionDeviceAdminReceiver
```

As device owner the app grants itself microphone and camera, disables the keyguard,
pins itself (lock task), and reopens after a reboot. Without device owner it still
works, but Android asks for the permissions once and a reboot shows its
notification instead of reopening the screen.

On a TV, waking the device turns the TV set on and switches its input only when
HDMI-CEC is enabled on both the TV and the Google TV device.
