package com.silvermind.companion.core

import com.silvermind.companion.core.CaptureLease.State
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class CaptureLeaseTest {
    private fun command(
        owner: String = "guided_task_start:12",
        mic: Boolean = true,
        camera: Boolean = false,
        lease: Int = 120,
    ) = HardwareCommand("kitchen", owner, "test", true, mic, camera, 65, null, lease)

    @Test
    fun `a lease runs out unless renewed`() {
        val lease = CaptureLease()
        lease.apply(command(), nowMs = 0)

        assertEquals(emptyList(), lease.expireDue(119_999))
        lease.apply(command(), nowMs = 100_000)
        assertEquals(emptyList(), lease.expireDue(200_000))
        assertEquals(listOf("guided_task_start:12"), lease.expireDue(220_000))
        assertEquals(State.AMBIENT, lease.state())
        assertNull(lease.nextExpiryMs())
    }

    @Test
    fun `one delivery ending never closes another's microphone`() {
        val lease = CaptureLease()
        lease.apply(command(), nowMs = 0)
        lease.apply(command(owner = "info_card:4", lease = 90), nowMs = 0)

        val afterCardCloses = lease.apply(command(owner = "info_card:4", mic = false, lease = 0), 10)

        assertEquals(State(screen = true, microphone = true, camera = false), afterCardCloses)
    }

    @Test
    fun `a screen-only command is a lease, not a release`() {
        val lease = CaptureLease()
        lease.apply(command(), nowMs = 0)

        val state = lease.apply(command(owner = "quiz:9", mic = false, lease = 630), nowMs = 1)

        assertEquals(State(screen = true, microphone = true, camera = false), state)
        assertEquals(listOf("guided_task_start:12"), lease.expireDue(120_000))
        assertEquals(State(screen = true, microphone = false, camera = false), lease.state())
        assertEquals(630_001, lease.nextExpiryMs())
    }

    @Test
    fun `the union of live leases decides the hardware`() {
        val lease = CaptureLease()
        lease.apply(command(mic = false, camera = true, lease = 30), nowMs = 0)
        lease.apply(command(owner = "quiz:9", mic = true, lease = 60), nowMs = 0)

        assertEquals(State(screen = true, microphone = true, camera = true), lease.state())
        lease.expireDue(30_000)
        assertEquals(State(screen = true, microphone = true, camera = false), lease.state())
    }
}
