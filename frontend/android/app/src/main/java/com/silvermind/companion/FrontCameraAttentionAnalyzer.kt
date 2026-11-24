package com.silvermind.companion

import androidx.annotation.OptIn
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import com.silvermind.companion.core.AttentionTracker
import java.util.concurrent.Executors

/**
 * Watches the front camera, about once a second, for a face turned toward the
 * screen, and reports only changes ("someone is facing it" / "nobody is").
 *
 * Detection runs on the device (ML Kit). Frames are analysed in memory and dropped:
 * no image, crop, or embedding is stored or sent, only presence and head angles.
 */
class FrontCameraAttentionAnalyzer(
    private val owner: LifecycleOwner,
    private val context: android.content.Context,
    private val onChange: (AttentionTracker.Attention) -> Unit,
) {
    private val tracker = AttentionTracker()
    private val executor = Executors.newSingleThreadExecutor()
    private val detector = FaceDetection.getClient(
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setMinFaceSize(0.15f)
            .build(),
    )
    private var provider: ProcessCameraProvider? = null
    private var analysis: ImageAnalysis? = null
    private var lastFrameMs = 0L

    fun start() {
        if (analysis != null) return
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val cameraProvider = future.get()
            val useCase = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also { it.setAnalyzer(executor, ::analyse) }
            cameraProvider.bindToLifecycle(owner, CameraSelector.DEFAULT_FRONT_CAMERA, useCase)
            provider = cameraProvider
            analysis = useCase
        }, ContextCompat.getMainExecutor(context))
    }

    fun stop() {
        analysis?.let { provider?.unbind(it) }
        analysis = null
        tracker.reset()
    }

    // ImageProxy.image is the only way to hand a CameraX frame to ML Kit without a copy;
    // the frame is closed on every path below, which is the contract the opt-in asks for.
    @OptIn(markerClass = [ExperimentalGetImage::class])
    private fun analyse(image: ImageProxy) {
        val now = System.currentTimeMillis()
        if (now - lastFrameMs < FRAME_INTERVAL_MS) {
            image.close()
            return
        }
        lastFrameMs = now
        val mediaImage = image.image
        if (mediaImage == null) {
            image.close()
            return
        }
        val input = InputImage.fromMediaImage(mediaImage, image.imageInfo.rotationDegrees)
        detector.process(input)
            .addOnSuccessListener { faces ->
                val readings = faces.map {
                    AttentionTracker.Face(yawDeg = it.headEulerAngleY, pitchDeg = it.headEulerAngleX)
                }
                tracker.update(readings, now)?.let(onChange)
            }
            .addOnCompleteListener { image.close() }
    }

    private companion object {
        const val FRAME_INTERVAL_MS = 1_000L
    }
}
