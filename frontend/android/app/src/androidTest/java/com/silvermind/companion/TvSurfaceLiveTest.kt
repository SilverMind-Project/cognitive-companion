package com.silvermind.companion

import android.app.UiModeManager
import android.content.Context
import android.content.res.Configuration
import android.view.KeyEvent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * One APK serves tablets and TVs: on a TV the page switches to its 10-foot layout
 * and a remote's D-pad moves focus between the on-screen controls.
 */
@RunWith(AndroidJUnit4::class)
class TvSurfaceLiveTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private fun isTelevision(): Boolean {
        val uiMode = instrumentation.targetContext.getSystemService(Context.UI_MODE_SERVICE) as UiModeManager
        return uiMode.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION
    }

    @Test
    fun the_page_uses_its_tv_layout_exactly_on_a_tv() {
        LiveCompanion.launchConnected().use { scenario ->
            val expected = isTelevision().toString()
            LiveCompanion.waitUntil("TV mode to match the device ($expected)", 15_000) {
                LiveCompanion.js(scenario, "document.documentElement.classList.contains('cc-tv-mode')") == expected
            }
        }
    }

    @Test
    fun the_remote_d_pad_moves_focus_between_controls_on_a_tv() {
        assumeTrue("D-pad navigation applies only on a TV", isTelevision())
        LiveCompanion.launchConnected().use { scenario ->
            val focused = "(() => { const el = document.activeElement;" +
                " return el && el !== document.body ? el.outerHTML.slice(0, 120) : ''; })()"

            instrumentation.sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_DOWN)
            LiveCompanion.waitUntil("the D-pad to focus a control", 5_000) {
                LiveCompanion.js(scenario, focused) != "\"\""
            }
            val first = LiveCompanion.js(scenario, focused)

            instrumentation.sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_DOWN)
            LiveCompanion.waitUntil("the D-pad to move focus", 5_000) {
                LiveCompanion.js(scenario, focused) != first
            }
            instrumentation.sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_UP)
            LiveCompanion.waitUntil("the D-pad to move focus back", 5_000) {
                LiveCompanion.js(scenario, focused) == first
            }
            assertNotEquals("\"\"", first)
            assertEquals(first, LiveCompanion.js(scenario, focused))
        }
    }
}
