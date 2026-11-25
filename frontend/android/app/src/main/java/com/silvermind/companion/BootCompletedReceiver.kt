package com.silvermind.companion

import android.app.admin.DevicePolicyManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Brings the companion back after a reboot with no one touching the device.
 *
 * The keep-alive service always starts. The screen itself is reopened only on a
 * device-owner kiosk, the one case Android lets an app start an activity from the
 * background; elsewhere the service's notification reopens it.
 */
class BootCompletedReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        try {
            CompanionForegroundService.start(context)
        } catch (e: IllegalStateException) {
            // Android 12+ may restrict background FGS starts; still launch kiosk activity below.
            Log.w("BootCompletedReceiver", "Foreground service start deferred at boot: ${e.message}")
        }
        val dpm = context.getSystemService(DevicePolicyManager::class.java)
        if (dpm.isDeviceOwnerApp(context.packageName)) {
            context.startActivity(
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
    }
}
