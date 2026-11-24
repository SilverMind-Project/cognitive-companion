package com.silvermind.companion

import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * The shell running the real, deployed companion page against the household server.
 *
 * These tests are live by design: they check what no unit test can, that the page
 * the household actually serves, the authenticated companion socket, and the native
 * plugin work together on a device with no tap. They run as their own registered,
 * room-less test surface with a dedicated test key, which `scripts/ccwin
 * test-instrumented` registers and passes in (it also refuses to start while a
 * guided routine is live, so the test socket cannot be mistaken for her tablet).
 *
 * Instrumentation arguments: `ccApiKey` (secret), `ccApiOrigin`, `ccSurfaceId`.
 */
object LiveCompanion {
    private const val API_KEY_STORAGE = "cc_api_key"
    private const val KIOSK_STORAGE = "cc_companion_kiosk_settings"
    const val PAGE_TIMEOUT_MS = 60_000L

    private fun arg(name: String): String =
        InstrumentationRegistry.getArguments().getString(name)?.takeIf { it.isNotBlank() }
            ?: error("missing instrumentation argument '$name'; run through scripts/ccwin test-instrumented")

    val apiKey: String get() = arg("ccApiKey")
    val apiOrigin: String get() = arg("ccApiOrigin").trimEnd('/')
    val surfaceId: String get() = arg("ccSurfaceId")

    /**
     * Load the page, give it the test key and the test surface (as a provisioned kiosk
     * would hold them), reload, and wait until its companion socket is connected.
     */
    fun launchConnected(): ActivityScenario<MainActivity> {
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        waitUntil("the companion page to load from the household server") {
            js(scenario, "document.readyState === 'complete' && location.protocol === 'https:'") == "true"
        }
        val settings = JSONObject()
            .put("kioskEnabled", true)
            .put("surfaceId", surfaceId)
            .put("roomId", JSONObject.NULL)
            .put("pin", "1234")
        js(
            scenario,
            "localStorage.setItem('$API_KEY_STORAGE', ${JSONObject.quote(apiKey)});" +
                "localStorage.setItem('$KIOSK_STORAGE', ${JSONObject.quote(settings.toString())});" +
                "location.reload(); 'reloading'",
        )
        waitUntil("the companion socket to connect") {
            js(scenario, "document.querySelector('[data-test=connection-status]')?.dataset.connected") ==
                "\"true\""
        }
        return scenario
    }

    /** Evaluate [script] in the page and return its JSON-encoded result. */
    fun js(scenario: ActivityScenario<MainActivity>, script: String): String {
        val latch = CountDownLatch(1)
        var result = "null"
        scenario.onActivity { activity ->
            activity.bridge.webView.evaluateJavascript(script) {
                result = it ?: "null"
                latch.countDown()
            }
        }
        check(latch.await(10, TimeUnit.SECONDS)) { "the page did not answer: $script" }
        return result
    }

    /** Ask the server to make this test surface identify itself (wake, chime, lease). */
    fun testSurface(microphone: Boolean): JSONObject {
        val url = URL("$apiOrigin/api/v1/companion-surfaces/$surfaceId/test")
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 10_000
            connection.readTimeout = 10_000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("x-api-key", apiKey)
            connection.outputStream.use {
                it.write(JSONObject().put("microphone", microphone).toString().toByteArray())
            }
            val status = connection.responseCode
            val body = (if (status < 400) connection.inputStream else connection.errorStream)
                ?.bufferedReader()?.use { it.readText() }.orEmpty()
            check(status == 200) { "POST ${url.path} returned $status: $body" }
            return JSONObject(body)
        } finally {
            connection.disconnect()
        }
    }

    fun waitUntil(what: String, timeoutMs: Long = PAGE_TIMEOUT_MS, condition: () -> Boolean) {
        val deadline = SystemClock.elapsedRealtime() + timeoutMs
        while (SystemClock.elapsedRealtime() < deadline) {
            if (runCatching(condition).getOrDefault(false)) return
            SystemClock.sleep(500)
        }
        throw AssertionError("timed out after ${timeoutMs / 1000} s waiting for $what")
    }
}
