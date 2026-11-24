package com.silvermind.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat

/**
 * Keeps the companion process alive and its network awake while the screen is off.
 *
 * The page's socket to the household server is how a wake command arrives, so it
 * must survive Doze and a dimmed screen. Idle, the service runs as `specialUse`
 * (a dedicated appliance); while the server holds a capture lease it is promoted to
 * `microphone` (and `camera`), which Android 14+ only allows while the activity is
 * visible, which the wake that precedes every lease guarantees.
 */
class CompanionForegroundService : Service() {
    private var wifiLock: WifiManager.WifiLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
        // A TV on Ethernet may have no Wi-Fi at all (and no WifiManager): it needs no
        // lock to keep its connection.
        wifiLock = getSystemService(WifiManager::class.java)
            ?.createWifiLock(WifiManager.WIFI_MODE_FULL_LOW_LATENCY, "companion:socket")
            ?.apply {
                setReferenceCounted(false)
                acquire()
            }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val microphone = intent?.getBooleanExtra(EXTRA_MICROPHONE, false) ?: false
        val camera = intent?.getBooleanExtra(EXTRA_CAMERA, false) ?: false
        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            notification(microphone, camera),
            foregroundTypes(microphone, camera),
        )
        return START_STICKY
    }

    /**
     * The service types to declare on this Android version. `specialUse` exists from
     * Android 14 and the capture types from Android 11; an older release has no such
     * type, and requires none, so it is declared without one rather than with a bit
     * that release does not define.
     */
    private fun foregroundTypes(microphone: Boolean, camera: Boolean): Int {
        var types = 0
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            if (microphone) types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            if (camera) types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA
        }
        return types
    }

    override fun onDestroy() {
        wifiLock?.release()
        wifiLock = null
        super.onDestroy()
    }

    private fun ensureChannel() {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Companion", NotificationManager.IMPORTANCE_LOW),
        )
    }

    private fun notification(microphone: Boolean, camera: Boolean): Notification {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val text = when {
            microphone && camera -> "Listening and camera active"
            microphone -> "Listening"
            camera -> "Camera active"
            else -> "Ready"
        }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("Cognitive Companion")
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val CHANNEL_ID = "companion"
        private const val NOTIFICATION_ID = 1
        private const val EXTRA_MICROPHONE = "microphone"
        private const val EXTRA_CAMERA = "camera"

        /** Start (or re-declare) the service for the capture now leased. */
        fun start(context: Context, microphone: Boolean = false, camera: Boolean = false) {
            val intent = Intent(context, CompanionForegroundService::class.java)
                .putExtra(EXTRA_MICROPHONE, microphone)
                .putExtra(EXTRA_CAMERA, camera)
            ContextCompat.startForegroundService(context, intent)
        }
    }
}
