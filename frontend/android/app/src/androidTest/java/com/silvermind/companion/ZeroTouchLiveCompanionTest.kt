package com.silvermind.companion

import android.Manifest
import android.content.Context
import android.os.PowerManager
import android.util.Log
import android.view.WindowManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.GrantPermissionRule
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The resident never taps: the household server wakes the screen, the page starts
 * listening, and the device closes the microphone itself when the lease runs out.
 */
@RunWith(AndroidJUnit4::class)
class ZeroTouchLiveCompanionTest {
    // The one-time Android permission a provisioned screen holds: a device-owner kiosk
    // grants it to itself, any other device asks once at setup. No tap is involved in
    // anything the tests then check.
    @get:Rule
    val microphonePermission: GrantPermissionRule = GrantPermissionRule.grant(Manifest.permission.RECORD_AUDIO)

    @Test
    fun the_page_may_play_audio_without_a_tap() {
        LiveCompanion.launchConnected().use { scenario ->
            scenario.onActivity { activity ->
                assertFalse(activity.bridge.webView.settings.mediaPlaybackRequiresUserGesture)
            }
        }
    }

    @Test
    fun the_page_is_granted_the_microphone_without_a_prompt_or_a_tap() {
        LiveCompanion.launchConnected().use { scenario ->
            // evaluateJavascript carries no user gesture, so this is the zero-tap path:
            // only the shell's own grant for its origin can let it through.
            LiveCompanion.js(
                scenario,
                "window.__ccMic = 'pending';" +
                    "navigator.mediaDevices.getUserMedia({audio: true})" +
                    ".then(s => { window.__ccMic = 'live:' + s.getAudioTracks()[0].readyState;" +
                    " s.getTracks().forEach(t => t.stop()); })" +
                    ".catch(e => { window.__ccMic = 'error:' + e.name; }); 'started'",
            )
            var outcome = "\"pending\""
            LiveCompanion.waitUntil("getUserMedia to settle", 15_000) {
                outcome = LiveCompanion.js(scenario, "window.__ccMic")
                outcome != "\"pending\""
            }
            Log.i(TAG, "getUserMedia outcome: $outcome")
            assertEquals("the microphone did not open: $outcome", "\"live:live\"", outcome)
        }
    }

    @Test
    fun a_server_command_wakes_the_screen_and_opens_the_microphone_until_its_lease_ends() {
        LiveCompanion.launchConnected().use { scenario ->
            // The server reached this surface's own socket: the command was routed to
            // this screen, not broadcast. The page names its surface when it connects,
            // so once it shows "connected" there is no unbound window to retry over.
            val result = LiveCompanion.testSurface(microphone = true)
            assertEquals(LiveCompanion.surfaceId, result.getString("surface_id"))
            assertTrue("the test surface was not connected: $result", result.getInt("reached") >= 1)
            val leaseMs = result.getInt("lease_seconds") * 1000L

            LiveCompanion.waitUntil("the screen to be held awake", 15_000) {
                keepsScreenOn(scenario) && isInteractive()
            }
            // The page started capture with no tap, and "Listening" shows only while the
            // microphone is really open.
            LiveCompanion.waitUntil("the page to show it is listening", 15_000) {
                LiveCompanion.js(scenario, "document.querySelector(${JSONObject.quote(LISTENING)}) !== null") == "true"
            }

            // No release is ever sent for a test: the device's own lease timer must
            // close the microphone and let the screen rest.
            val eitherPill = JSONObject.quote("$LISTENING, $MIC_UNAVAILABLE")
            LiveCompanion.waitUntil("the lease to end capture", leaseMs + 20_000) {
                !keepsScreenOn(scenario) &&
                    LiveCompanion.js(scenario, "document.querySelector($eitherPill) === null") == "true"
            }
        }
    }

    private companion object {
        const val TAG = "CompanionLiveTest"
        const val LISTENING = "[data-test=capture-mic]"
        const val MIC_UNAVAILABLE = "[data-test=capture-mic-unavailable]"
    }

    private fun keepsScreenOn(scenario: androidx.test.core.app.ActivityScenario<MainActivity>): Boolean {
        var flags = 0
        scenario.onActivity { flags = it.window.attributes.flags }
        return flags and WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON != 0
    }

    private fun isInteractive(): Boolean =
        InstrumentationRegistry.getInstrumentation().targetContext
            .getSystemService(Context.POWER_SERVICE).let { (it as PowerManager).isInteractive }
}
