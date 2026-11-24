package com.silvermind.companion.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class HardwareCommandTest {
    @Test
    fun `parses the server command`() {
        val command = HardwareCommand.fromMap(
            mapOf(
                "type" to "surface_hardware_command",
                "surface_id" to "kitchen-tablet",
                "lease_owner" to "guided_task_start:12",
                "reason" to "guided_task_start",
                "wake_screen" to true,
                "enable_microphone" to true,
                "enable_camera" to false,
                "volume_min_pct" to 65,
                "attention_chime" to "gentle",
                "lease_seconds" to 330,
            ),
        )

        assertEquals("kitchen-tablet", command.surfaceId)
        assertEquals("guided_task_start:12", command.leaseOwner)
        assertTrue(command.wakeScreen)
        assertTrue(command.captures)
        assertEquals(65, command.volumeMinPct)
        assertEquals("gentle", command.attentionChime)
        assertEquals(330, command.leaseSeconds)
    }

    @Test
    fun `missing or mistyped fields take the safe value`() {
        val command = HardwareCommand.fromMap(
            mapOf("enable_microphone" to "yes", "lease_seconds" to 999_999, "volume_min_pct" to 250),
        )

        assertFalse(command.enableMicrophone)
        assertFalse(command.wakeScreen)
        assertFalse(command.captures)
        assertEquals(HardwareCommand.MAX_LEASE_SECONDS, command.leaseSeconds)
        assertEquals(100, command.volumeMinPct)
        assertNull(HardwareCommand.fromMap(emptyMap()).volumeMinPct)
    }
}
