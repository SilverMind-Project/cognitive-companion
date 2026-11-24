package com.silvermind.companion

import android.Manifest
import android.app.KeyguardManager
import android.app.UiModeManager
import android.content.Context
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.view.WindowManager
import androidx.core.content.ContextCompat
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.silvermind.companion.core.AttentionTracker
import com.silvermind.companion.core.CaptureLease
import com.silvermind.companion.core.HardwareCommand
import com.silvermind.companion.core.VolumeFloor

/**
 * The page's handle on the device: wake the screen, make it audible, and lease the
 * microphone and front camera for as long as the server says.
 *
 * Called from `useNativeCompanionHardware.js` with each `surface_hardware_command`.
 * The audio itself is captured by the page (WebView getUserMedia, with its echo
 * cancellation); this plugin only makes the device ready for it and runs the
 * camera attention check. Leases are per delivery (`lease_owner`); the device holds
 * the union of the live ones, and enforces them here as well as in the page, so a
 * suspended page still closes capture on time.
 *
 * Events: `facePresenceChanged` ({facePresent, yaw, pitch}) and `leaseExpired`
 * ({owners}).
 */
@CapacitorPlugin(name = "CompanionHardware")
class CompanionHardwarePlugin : Plugin() {
    private val main = Handler(Looper.getMainLooper())
    private val lease = CaptureLease()
    private var camera: FrontCameraAttentionAnalyzer? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val expireLease = Runnable { onLeaseTimer() }

    @PluginMethod
    fun getDeviceInfo(call: PluginCall) {
        val ctx = context
        val uiMode = ctx.getSystemService(UiModeManager::class.java).currentModeType
        val television = uiMode == Configuration.UI_MODE_TYPE_TELEVISION ||
            ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_LEANBACK)
        call.resolve(
            JSObject()
                .put("isTelevision", television)
                .put("hasFrontCamera", ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_FRONT)),
        )
    }

    @PluginMethod
    fun applyCommand(call: PluginCall) {
        val command = HardwareCommand.fromMap(call.data.toMap())
        main.post {
            if (command.wakeScreen) wakeScreen()
            setVolumeFloor(command.volumeMinPct)
            if (command.attentionChime != null && command.leaseSeconds > 0) playChime()

            applyState(lease.apply(command, System.currentTimeMillis()))
            call.resolve(JSObject().put("screenAwake", isScreenAwake()))
        }
    }

    override fun handleOnDestroy() {
        main.removeCallbacks(expireLease)
        camera?.stop()
        releaseWakeLock()
        super.handleOnDestroy()
    }

    private fun onLeaseTimer() {
        val expired = lease.expireDue(System.currentTimeMillis())
        applyState(lease.state())
        if (expired.isNotEmpty()) {
            val owners = com.getcapacitor.JSArray().apply { expired.forEach { put(it) } }
            notifyListeners("leaseExpired", JSObject().put("owners", owners))
        }
    }

    /**
     * Make the hardware match the live leases and time the next expiry. With none
     * live the device returns to ambient: camera off, the screen may sleep, the
     * service idles.
     */
    private fun applyState(state: CaptureLease.State) {
        main.removeCallbacks(expireLease)
        setCamera(state.camera)
        keepScreenOn(state.screen)
        if (!state.screen) releaseWakeLock()
        promoteService(state.microphone, state.camera)
        lease.nextExpiryMs()?.let {
            main.postDelayed(expireLease, (it - System.currentTimeMillis()).coerceAtLeast(0))
        }
    }

    /**
     * Turn the screen on (and, on a TV, the TV set through HDMI-CEC, which Android TV
     * sends when the device leaves standby) and bring the companion to the front.
     */
    private fun wakeScreen() {
        val activity = activity ?: return
        val power = activity.getSystemService(PowerManager::class.java)
        if (wakeLock?.isHeld != true) {
            @Suppress("DEPRECATION") // The only wake lock that can turn a screen on.
            wakeLock = power.newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "companion:wake",
            ).apply { acquire(WAKE_LOCK_MAX_MS) }
        }
        activity.setTurnScreenOn(true)
        activity.getSystemService(KeyguardManager::class.java).requestDismissKeyguard(activity, null)
    }

    private fun releaseWakeLock() {
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
    }

    private fun keepScreenOn(on: Boolean) {
        val window = activity?.window ?: return
        if (on) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }

    private fun isScreenAwake(): Boolean =
        context.getSystemService(PowerManager::class.java).isInteractive

    private fun setVolumeFloor(minPct: Int?) {
        val audio = context.getSystemService(AudioManager::class.java)
        val stream = AudioManager.STREAM_MUSIC
        VolumeFloor.target(audio.getStreamVolume(stream), audio.getStreamMaxVolume(stream), minPct)
            ?.let { audio.setStreamVolume(stream, it, 0) }
    }

    private fun playChime() {
        MediaPlayer.create(context, R.raw.gentle_chime)?.apply {
            setOnCompletionListener { it.release() }
            start()
        }
    }

    private fun setCamera(on: Boolean) {
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED
        if (on && granted) {
            val owner = activity ?: return
            val analyzer = camera ?: FrontCameraAttentionAnalyzer(owner, context, ::onAttention)
                .also { camera = it }
            analyzer.start()
        } else {
            camera?.stop()
        }
    }

    private fun onAttention(attention: AttentionTracker.Attention) {
        val event = JSObject().put("facePresent", attention.facePresent)
        attention.face?.let { event.put("yaw", it.yawDeg).put("pitch", it.pitchDeg) }
        notifyListeners("facePresenceChanged", event)
    }

    /**
     * Declare the capture to Android. A refused promotion (a permission not yet
     * granted, or a start from the background) leaves the service as it was; the page's capture still works
     * while the screen is on.
     */
    private fun promoteService(microphone: Boolean, camera: Boolean) {
        val ctx = context
        val mic = microphone && granted(ctx, Manifest.permission.RECORD_AUDIO)
        val cam = camera && granted(ctx, Manifest.permission.CAMERA)
        try {
            CompanionForegroundService.start(ctx, microphone = mic, camera = cam)
        } catch (e: SecurityException) {
            android.util.Log.w(TAG, "companion_service_promotion_refused", e)
        } catch (e: IllegalStateException) {
            // ForegroundServiceStartNotAllowedException (Android 12+): a lease timer
            // fired while the app was in the background. Capture is already closed;
            // the service keeps its previous declaration until the next wake.
            android.util.Log.w(TAG, "companion_service_promotion_deferred", e)
        }
    }

    private fun granted(ctx: Context, permission: String) =
        ContextCompat.checkSelfPermission(ctx, permission) == PackageManager.PERMISSION_GRANTED

    private fun org.json.JSONObject.toMap(): Map<String, Any?> =
        keys().asSequence().associateWith { key -> opt(key).takeUnless { it == org.json.JSONObject.NULL } }

    private companion object {
        const val TAG = "CompanionHardware"
        // A wake lock is a backstop only: the lease and keep-screen-on govern the screen.
        const val WAKE_LOCK_MAX_MS = 60_000L
    }
}
