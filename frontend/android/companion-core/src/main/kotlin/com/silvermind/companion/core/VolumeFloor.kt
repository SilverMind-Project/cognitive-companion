package com.silvermind.companion.core

/**
 * The volume a device must be raised to so a spoken prompt is audible.
 *
 * Only ever raises: a device already louder than the floor is left alone, so the
 * floor never turns down a volume a hard-of-hearing resident's family set high.
 */
object VolumeFloor {
    /**
     * The stream index to set, or null to leave the volume as it is.
     *
     * [current] and [max] are the platform's stream indices; [minPct] is the
     * server's floor as a share of [max] (null for no floor). Rounds up, so a floor
     * of 65% on a 15-step stream is step 10, never the quieter step 9.
     */
    fun target(current: Int, max: Int, minPct: Int?): Int? {
        if (minPct == null || max <= 0) return null
        val floor = ((max * minPct.coerceIn(0, 100)) + 99) / 100
        return if (current < floor) floor else null
    }
}
