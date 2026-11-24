package com.silvermind.companion.core

import kotlin.math.abs

/**
 * Turns per-frame face detections into "is someone facing the screen" changes.
 *
 * Only changes are reported, so a still resident does not produce a message every
 * frame. A reading must hold for [holdMs] before it is reported, so one missed
 * detection (a blink, a turned head) does not flap the state. Nothing here keeps or
 * returns an image: only presence and the facing face's head angles.
 */
class AttentionTracker(
    private val holdMs: Long = 1500,
    private val maxYawDeg: Float = 30f,
    private val maxPitchDeg: Float = 25f,
) {
    /** Head angles of one detected face, in degrees. */
    data class Face(val yawDeg: Float, val pitchDeg: Float)

    /** A reported change: [face] is the face judged to be looking, if any. */
    data class Attention(val facePresent: Boolean, val face: Face?)

    private var reported: Boolean? = null
    private var candidate: Boolean? = null
    private var candidateSinceMs: Long = 0

    /** Feed one analysed frame; returns a change to report, or null. */
    fun update(faces: List<Face>, nowMs: Long): Attention? {
        val facing = faces
            .filter { abs(it.yawDeg) <= maxYawDeg && abs(it.pitchDeg) <= maxPitchDeg }
            .minByOrNull { abs(it.yawDeg) + abs(it.pitchDeg) }
        val present = facing != null
        if (present != candidate) {
            candidate = present
            candidateSinceMs = nowMs
        }
        if (present == reported || nowMs - candidateSinceMs < holdMs) return null
        reported = present
        return Attention(present, facing)
    }

    /** Forget the reported state (the camera stopped), so the next start reports afresh. */
    fun reset() {
        reported = null
        candidate = null
    }
}
