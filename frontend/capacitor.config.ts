import type { CapacitorConfig } from "@capacitor/cli";

/*
 * The Android companion shell (tablet and Google TV / Android TV) loads the
 * companion page from the household server rather than bundling it: the page and
 * the API then share one HTTPS origin, so microphone access (secure context only),
 * relative API calls, and the companion socket all work unchanged, and every
 * deploy updates the shell without a new APK. Set CC_COMPANION_URL at `cap sync`
 * time to point a build at another server; it must be HTTPS.
 *
 * `webDir` is only the offline fallback Capacitor requires; the appId is
 * permanent once a device is provisioned as device owner with it.
 */
// No default: a wrong origin would ship an app that can never connect. For this
// household it is https://nanai.khoofia.com/companion?kiosk=1 (the cluster ingress,
// kubernetes/edge/ at the workspace root); the app it loads calls the API on
// https://api.nanai.khoofia.com.
const companionUrl = process.env.CC_COMPANION_URL ?? "";

if (!companionUrl.startsWith("https://")) {
  throw new Error(
    `Set CC_COMPANION_URL to the household server's https:// companion page (got "${companionUrl}")`,
  );
}

const config: CapacitorConfig = {
  appId: "com.silvermind.companion",
  appName: "Cognitive Companion",
  webDir: "dist",
  server: {
    url: companionUrl,
    cleartext: false,
    allowNavigation: [new URL(companionUrl).host],
  },
  android: {
    allowMixedContent: false,
  },
};

export default config;
