package com.silvermind.companion

import android.Manifest
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.webkit.PermissionRequest
import androidx.core.net.toUri
import com.getcapacitor.BridgeActivity
import com.getcapacitor.BridgeWebChromeClient

/**
 * The companion screen: the household server's companion page in a WebView that may
 * play audio and capture the microphone without a tap.
 *
 * A resident with dementia cannot be expected to walk up to a sleeping tablet and
 * tap "Begin" after every reboot or crash, which is all a browser would allow. Here
 * the page can be woken, heard, and listen as soon as the server asks, and the
 * Android shell only moves bytes: what to say and when to listen is decided by the
 * server and the page.
 */
class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(CompanionHardwarePlugin::class.java)
        super.onCreate(savedInstanceState)

        // Shown over the lock screen and allowed to turn the screen on, so a wake
        // command from the server is seen without unlocking.
        setShowWhenLocked(true)
        setTurnScreenOn(true)

        val webView = bridge.webView
        webView.settings.mediaPlaybackRequiresUserGesture = false
        webView.webChromeClient = CompanionChromeClient(this)

        if (isDeviceOwner()) enterKiosk()
        CompanionForegroundService.start(this)
    }

    private fun isDeviceOwner(): Boolean =
        getSystemService(DevicePolicyManager::class.java).isDeviceOwnerApp(packageName)

    /**
     * As device owner (provisioned once with `adb shell dpm set-device-owner`), grant
     * the capture permissions silently, keep the keyguard away, and pin the app so a
     * stray touch cannot leave it.
     */
    private fun enterKiosk() {
        val dpm = getSystemService(DevicePolicyManager::class.java)
        val admin = CompanionDeviceAdminReceiver.component(this)
        for (permission in kioskPermissions()) {
            dpm.setPermissionGrantState(
                admin,
                packageName,
                permission,
                DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED,
            )
        }
        dpm.setKeyguardDisabled(admin, true)
        dpm.setLockTaskPackages(admin, arrayOf(packageName))
        startLockTask()
    }

    /**
     * Lets the page's own origin capture the microphone and camera; any other origin,
     * or any request for anything else, is denied.
     *
     * Granting the WebView's request is not enough on its own: Chromium can open the
     * microphone only if the app holds Android's RECORD_AUDIO (CAMERA) permission, or it
     * fails with NotReadableError. Capacitor's handler asks Android for exactly those
     * permissions before granting, so an own-origin capture request is handed to it. A
     * device-owner kiosk already holds them (granted silently in [enterKiosk]), so no
     * prompt is shown there; any other device asks once, at setup.
     */
    private class CompanionChromeClient(private val activity: MainActivity) :
        BridgeWebChromeClient(activity.bridge) {
        override fun onPermissionRequest(request: PermissionRequest) {
            val ownOrigin = activity.bridge.serverUrl?.toUri()
            val fromOwnOrigin = ownOrigin != null &&
                request.origin.scheme == ownOrigin.scheme &&
                request.origin.host == ownOrigin.host
            val captureOnly = request.resources.isNotEmpty() &&
                request.resources.all { it in CAPTURE_RESOURCES }
            if (fromOwnOrigin && captureOnly) {
                super.onPermissionRequest(request)
            } else {
                request.deny()
            }
        }
    }

    companion object {
        /** The runtime permissions a kiosk grants itself; notifications are one only from Android 13. */
        private fun kioskPermissions(): List<String> = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            add(Manifest.permission.CAMERA)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        private val CAPTURE_RESOURCES = setOf(
            PermissionRequest.RESOURCE_AUDIO_CAPTURE,
            PermissionRequest.RESOURCE_VIDEO_CAPTURE,
        )

        fun component(context: Context) = ComponentName(context, MainActivity::class.java)
    }
}
