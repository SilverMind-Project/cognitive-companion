package com.silvermind.companion.core

/**
 * The bounded windows in which the device may keep its screen awake and its
 * microphone and camera open, one per delivery.
 *
 * Every delivery (a guided session, a quiz, a card) holds its own lease, keyed by
 * its owner, and renews it by sending again; the device keeps the screen awake while
 * any lease is live and the microphone (camera) open while any live lease asks for
 * it. One delivery ending therefore never closes another's microphone. If a release
 * is lost (a dropped socket, a crashed page), the lease runs out and the device
 * closes capture on its own, so a microphone or camera can never stay open
 * indefinitely. Time is injected as epoch milliseconds.
 */
class CaptureLease {
    /** One delivery's lease. */
    data class Grant(val microphone: Boolean, val camera: Boolean, val expiresAtMs: Long)

    /** What the device should have now: the union of the live leases. */
    data class State(val screen: Boolean, val microphone: Boolean, val camera: Boolean) {
        companion object {
            val AMBIENT = State(screen = false, microphone = false, camera = false)
        }
    }

    private val grants = mutableMapOf<String, Grant>()

    /** Apply a command at [nowMs] (start, renew, or end its owner's lease). */
    fun apply(command: HardwareCommand, nowMs: Long): State {
        if (command.leaseSeconds > 0) {
            grants[command.leaseOwner] = Grant(
                microphone = command.enableMicrophone,
                camera = command.enableCamera,
                expiresAtMs = nowMs + command.leaseSeconds * 1000L,
            )
        } else {
            grants.remove(command.leaseOwner)
        }
        return state()
    }

    /** End every lease that has run out by [nowMs]; returns their owners. */
    fun expireDue(nowMs: Long): List<String> {
        val expired = grants.filterValues { nowMs >= it.expiresAtMs }.keys.toList()
        expired.forEach(grants::remove)
        return expired
    }

    /** When the next live lease runs out, or null when none is live. */
    fun nextExpiryMs(): Long? = grants.values.minOfOrNull { it.expiresAtMs }

    fun state(): State = if (grants.isEmpty()) {
        State.AMBIENT
    } else {
        State(
            screen = true,
            microphone = grants.values.any { it.microphone },
            camera = grants.values.any { it.camera },
        )
    }
}
