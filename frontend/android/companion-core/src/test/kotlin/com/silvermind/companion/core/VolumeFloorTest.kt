package com.silvermind.companion.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class VolumeFloorTest {
    @Test
    fun `raises a quiet device to the floor, rounding up`() {
        assertEquals(10, VolumeFloor.target(current = 0, max = 15, minPct = 65))
        assertEquals(10, VolumeFloor.target(current = 9, max = 15, minPct = 65))
    }

    @Test
    fun `never turns a loud device down, and no floor means no change`() {
        assertNull(VolumeFloor.target(current = 14, max = 15, minPct = 65))
        assertNull(VolumeFloor.target(current = 10, max = 15, minPct = 65))
        assertNull(VolumeFloor.target(current = 0, max = 15, minPct = null))
        assertNull(VolumeFloor.target(current = 0, max = 0, minPct = 65))
    }
}
