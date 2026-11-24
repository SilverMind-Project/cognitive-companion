package com.silvermind.companion

import android.app.admin.DeviceAdminReceiver
import android.content.ComponentName
import android.content.Context

/** The device-owner admin for a dedicated companion tablet or TV (kiosk mode). */
class CompanionDeviceAdminReceiver : DeviceAdminReceiver() {
    companion object {
        fun component(context: Context) =
            ComponentName(context, CompanionDeviceAdminReceiver::class.java)
    }
}
