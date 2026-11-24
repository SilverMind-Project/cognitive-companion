package com.silvermind.companion.core

/**
 * One `surface_hardware_command` from the household server, as the web page hands
 * it to the native plugin. Field names and meaning mirror the backend schema
 * `SurfaceHardwareCommand` (backend/schemas/companion_surface_ws.py).
 *
 * Leases are per [leaseOwner] (one delivery: a guided session, a quiz, a card). A
 * command with `leaseSeconds == 0` ends that owner's lease; a command that wakes the
 * screen without capture is a screen-only lease, never a release.
 */
data class HardwareCommand(
    val surfaceId: String,
    val leaseOwner: String,
    val reason: String,
    val wakeScreen: Boolean,
    val enableMicrophone: Boolean,
    val enableCamera: Boolean,
    val volumeMinPct: Int?,
    val attentionChime: String?,
    val leaseSeconds: Int,
) {
    val captures: Boolean get() = enableMicrophone || enableCamera

    companion object {
        /** The server caps a lease at an hour; a larger value is treated as that. */
        const val MAX_LEASE_SECONDS = 3600

        /**
         * Parse the JSON-shaped map the page sent. Missing or mistyped fields take the
         * safe value: nothing enabled, no volume change, no lease.
         */
        fun fromMap(raw: Map<String, Any?>): HardwareCommand = HardwareCommand(
            surfaceId = raw["surface_id"] as? String ?: "",
            leaseOwner = raw["lease_owner"] as? String ?: "",
            reason = raw["reason"] as? String ?: "",
            wakeScreen = raw["wake_screen"] as? Boolean ?: false,
            enableMicrophone = raw["enable_microphone"] as? Boolean ?: false,
            enableCamera = raw["enable_camera"] as? Boolean ?: false,
            volumeMinPct = (raw["volume_min_pct"] as? Number)?.toInt()?.coerceIn(0, 100),
            attentionChime = raw["attention_chime"] as? String,
            leaseSeconds = ((raw["lease_seconds"] as? Number)?.toInt() ?: 0)
                .coerceIn(0, MAX_LEASE_SECONDS),
        )
    }
}
