package com.silvermind.companion.core

import com.silvermind.companion.core.AttentionTracker.Face
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class AttentionTrackerTest {
    private val facing = listOf(Face(yawDeg = -4.2f, pitchDeg = 1.5f))
    private val lookingAway = listOf(Face(yawDeg = 70f, pitchDeg = 0f))

    @Test
    fun `reports a change only after it holds`() {
        val tracker = AttentionTracker(holdMs = 1_000)

        assertNull(tracker.update(facing, nowMs = 0))
        assertNull(tracker.update(facing, nowMs = 999))
        assertEquals(AttentionTracker.Attention(true, facing[0]), tracker.update(facing, nowMs = 1_000))
        assertNull(tracker.update(facing, nowMs = 5_000))
    }

    @Test
    fun `a single missed frame does not flap the state`() {
        val tracker = AttentionTracker(holdMs = 1_000)
        tracker.update(facing, 0)
        tracker.update(facing, 1_000)

        assertNull(tracker.update(emptyList(), 1_200))
        assertNull(tracker.update(facing, 1_400))
        assertNull(tracker.update(facing, 3_000))
    }

    @Test
    fun `a face turned away is not attention`() {
        val tracker = AttentionTracker(holdMs = 0)

        assertEquals(AttentionTracker.Attention(false, null), tracker.update(lookingAway, 0))
        val best = Face(2f, 2f)
        assertEquals(
            AttentionTracker.Attention(true, best),
            tracker.update(lookingAway + Face(20f, 10f) + best, 1),
        )
    }

    @Test
    fun `reset reports the state afresh`() {
        val tracker = AttentionTracker(holdMs = 0)
        tracker.update(facing, 0)
        tracker.reset()

        assertEquals(AttentionTracker.Attention(true, facing[0]), tracker.update(facing, 1))
    }
}
