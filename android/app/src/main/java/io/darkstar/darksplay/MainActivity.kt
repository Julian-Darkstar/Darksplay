package io.darkstar.darksplay

import android.app.Activity
import android.os.Bundle
import android.os.Build
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.View
import android.widget.Button
import android.widget.TextView

class MainActivity : Activity(), SurfaceHolder.Callback {
    private val lifecycle = ReceiverLifecycle<SessionReceiver>()
    private var resumed = false
    private lateinit var video: SurfaceView
    private lateinit var start: Button
    private lateinit var stop: Button
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        val content = findViewById<View>(R.id.content)
        content.setOnApplyWindowInsetsListener { view, insets ->
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars())
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            } else {
                @Suppress("DEPRECATION")
                view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                    insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            }
            insets
        }
        video = findViewById(R.id.video)
        start = findViewById(R.id.start_receiver)
        stop = findViewById(R.id.stop_receiver)
        status = findViewById(R.id.status)
        video.holder.addCallback(this)
        updateButtons()
        start.setOnClickListener {
            val session = lifecycle.start() ?: return@setOnClickListener
            updateButtons()
            session.start()
        }
        stop.setOnClickListener { stopReceiver() }
    }

    private fun prepareReceiver() {
        if (!lifecycle.canPrepare) return
        lateinit var session: SessionReceiver
        session = SessionReceiver(video.holder.surface,
            { text -> runOnUiThread {
                if (lifecycle.receiver === session) status.text = text
            } },
            { runOnUiThread {
                lifecycle.prepared(session)
                updateButtons()
            } },
            { runOnUiThread {
                val replace = lifecycle.phase != ReceiverLifecycle.Phase.PREPARING
                if (lifecycle.finished(session)) {
                    // Re-arm transport after cleanup, but never retry a failed preparation.
                    if (replace) prepareReceiver()
                    updateButtons()
                }
            } })
        lifecycle.attach(session)
        updateButtons()
        session.prepare() // Transport only; Start remains the session authorization.
    }

    private fun updateButtons() {
        start.isEnabled = lifecycle.canStart
        stop.isEnabled = lifecycle.phase == ReceiverLifecycle.Phase.STARTED
    }

    private fun surfaceAvailable() {
        lifecycle.available = resumed && video.holder.surface.isValid
        prepareReceiver()
        updateButtons()
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        surfaceAvailable()
    }

    private fun stopReceiver() {
        val session = lifecycle.stop()
        updateButtons()
        session?.stop()
    }

    override fun onStop() {
        resumed = false
        lifecycle.available = false
        stopReceiver()
        super.onStop()
    }
    override fun surfaceCreated(holder: SurfaceHolder) { surfaceAvailable() }
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) = Unit
    override fun surfaceDestroyed(holder: SurfaceHolder) {
        lifecycle.available = false
        stopReceiver()
    }
}
