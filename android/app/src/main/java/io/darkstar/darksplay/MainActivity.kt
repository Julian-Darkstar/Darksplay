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
    private var receiver: VideoReceiver? = null
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
        video.holder.setFixedSize(1280, 720)
        video.holder.addCallback(this)
        start = findViewById(R.id.start_receiver)
        stop = findViewById(R.id.stop_receiver)
        status = findViewById(R.id.status)
        start.setOnClickListener {
            if (receiver == null && video.holder.surface.isValid) {
                start.isEnabled = false
                stop.isEnabled = true
                val session = VideoReceiver(video.holder.surface,
                    { text -> runOnUiThread { status.text = text } },
                    { runOnUiThread {
                        receiver = null
                        start.isEnabled = video.holder.surface.isValid
                        stop.isEnabled = false
                    } })
                receiver = session
                session.start()
            }
        }
        stop.setOnClickListener { stopReceiver() }
    }

    private fun stopReceiver() {
        stop.isEnabled = false
        receiver?.stop()
    }

    override fun onStop() {
        stopReceiver()
        super.onStop()
    }
    override fun surfaceCreated(holder: SurfaceHolder) { start.isEnabled = receiver == null }
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) = Unit
    override fun surfaceDestroyed(holder: SurfaceHolder) {
        start.isEnabled = false
        stopReceiver()
    }
}
