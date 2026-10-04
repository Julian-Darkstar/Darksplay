package io.darkstar.darksplay

import android.media.MediaCodec
import android.media.MediaFormat
import android.net.LocalServerSocket
import android.net.LocalSocket
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.system.Os
import android.system.OsConstants
import android.system.StructPollfd
import android.view.Surface
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicLong

/** One explicitly armed session, one worker, no persistent Android service. */
internal class VideoReceiver(private val surface: Surface, private val config: VideoConfig,
    private val report: (String) -> Unit, private val connected: () -> Unit,
    private val finished: () -> Unit) {
    @Volatile private var stopping = false
    private val lock = Any()
    private var server: LocalServerSocket? = null
    private var socket: LocalSocket? = null
    private val rendered = AtomicLong()
    private var worker: Thread? = null

    fun prepare() {
        synchronized(lock) {
            check(!stopping) { "Session stopped" }
            server = LocalServerSocket(SOCKET_NAME)
        }
    }

    fun awaitTermination() { worker?.join(3000) }
    fun isAlive(): Boolean = worker?.isAlive == true

    fun start() {
        worker = Thread({ runSession() }, "DarksplayVideo").also { it.start() }
    }

    fun stop() {
        stopping = true
        synchronized(lock) {
            // shutdown wakes a blocked read/accept; worker owns codec teardown.
            runCatching { socket?.shutdownInput() }
            runCatching { socket?.close() }
            runCatching { server?.let { Os.shutdown(it.fileDescriptor, OsConstants.SHUT_RDWR) } }
            runCatching { server?.close() }
        }
    }

    private fun runSession() {
        var codec: MediaCodec? = null
        var codecStarted = false
        var received = 0L
        var queued = 0L
        var released = 0L
        var lastStats = SystemClock.elapsedRealtime()
        val beginning = lastStats
        var previousRendered = 0L
        var reason = "Stream terminado"
        try {
            if (stopping) return
            Log.i(TAG, "configured video receiver; localabstract:$SOCKET_NAME prepared")
            val listener = server ?: error("Video listener not prepared")
            val poll = StructPollfd().apply {
                fd = listener.fileDescriptor
                events = OsConstants.POLLIN.toShort()
            }
            check(Os.poll(arrayOf(poll), 5000) > 0) { "Video connection timeout" }
            val accepted = listener.accept()
            synchronized(lock) {
                if (stopping) { accepted.close(); return }
                socket = accepted
                server?.close()
                server = null
            }
            connected()
            accepted.soTimeout = 5000
            Log.i(TAG, "ADB connection accepted")
            val reader = AnnexBReader(accepted.inputStream)
            val first = reader.nextAccessUnit() ?: error("Stream vacío")
            Log.i(TAG, "first data received; access unit bytes=${first.size}")
            val format = MediaFormat.createVideoFormat(config.mime, config.width, config.height).apply {
                setInteger(MediaFormat.KEY_FRAME_RATE, config.fps)
                setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, AnnexBReader.MAX_BYTES)
                setByteBuffer("csd-0", ByteBuffer.wrap(AnnexBReader.parameterSet(first, 7)))
                setByteBuffer("csd-1", ByteBuffer.wrap(AnnexBReader.parameterSet(first, 8)))
            }
            val decoder = MediaCodec.createDecoderByType(config.mime)
            codec = decoder
            decoder.configure(format, surface, null, 0)
            decoder.setOnFrameRenderedListener({ _, _, _ ->
                if (rendered.incrementAndGet() == 1L) {
                    Log.i(TAG, "first frame rendered to Surface")
                    report("Vídeo recibido: ${config.width}×${config.height} / ${config.fps} FPS nominales")
                }
            }, Handler(Looper.getMainLooper()))
            decoder.start()
            codecStarted = true
            Log.i(TAG, "MediaCodec configured: ${decoder.name}; $format")
            val info = MediaCodec.BufferInfo()
            fun drain(): Boolean {
                while (!stopping) {
                    val index = decoder.dequeueOutputBuffer(info, 0)
                    when {
                        index >= 0 -> {
                            val eos = (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0
                            val image = info.size > 0
                            decoder.releaseOutputBuffer(index, image)
                            if (image) released++
                            if (eos) return true
                        }
                        index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED ->
                            Log.i(TAG, "output format: ${decoder.outputFormat}")
                        else -> return false
                    }
                }
                return false
            }
            fun queue(bytes: ByteArray?, pts: Long) {
                val deadline = SystemClock.elapsedRealtime() + 5000
                while (!stopping) {
                    drain()
                    val index = decoder.dequeueInputBuffer(10_000)
                    if (index >= 0) {
                        val buffer = decoder.getInputBuffer(index) ?: error("Missing input buffer")
                        buffer.clear()
                        require((bytes?.size ?: 0) <= buffer.remaining()) { "Codec input buffer too small" }
                        if (bytes != null) buffer.put(bytes)
                        decoder.queueInputBuffer(index, 0, bytes?.size ?: 0, pts,
                            if (bytes == null) MediaCodec.BUFFER_FLAG_END_OF_STREAM else 0)
                        return
                    }
                    check(SystemClock.elapsedRealtime() < deadline) { "Decoder stalled for 5 seconds" }
                }
            }
            var unit: ByteArray? = first
            while (!stopping && unit != null) {
                received += unit.size
                queue(unit, queued * 1_000_000 / config.fps)
                queued++
                drain()
                val now = SystemClock.elapsedRealtime()
                if (now - lastStats >= 5000) {
                    val frames = rendered.get()
                    val fps = (frames - previousRendered) * 1000.0 / (now - lastStats)
                    Log.i(TAG, "stats elapsedMs=${now - beginning} bytes=$received queued=$queued " +
                        "released=$released rendered=$frames fps=$fps pending=${queued - released}")
                    previousRendered = frames
                    lastStats = now
                }
                unit = reader.nextAccessUnit()
            }
            if (!stopping) {
                queue(null, queued * 1_000_000 / config.fps)
                val deadline = SystemClock.elapsedRealtime() + 2000
                while (!stopping && !drain() && SystemClock.elapsedRealtime() < deadline) Thread.sleep(5)
            }
        } catch (error: Exception) {
            if (!stopping) {
                reason = "Stream detenido: ${error.message}"
                Log.e(TAG, "receiver error", error)
            }
        } finally {
            synchronized(lock) {
                runCatching { socket?.close() }
                runCatching { server?.close() }
                socket = null
                server = null
            }
            if (codecStarted) runCatching { codec?.stop() }.onFailure { Log.w(TAG, "codec stop", it) }
            runCatching { codec?.release() }.onFailure { Log.w(TAG, "codec release", it) }
            Log.i(TAG, "decoder stopped; queued=$queued released=$released rendered=${rendered.get()} " +
                "elapsedMs=${SystemClock.elapsedRealtime() - beginning}")
            report(if (stopping) "Receiver detenido" else reason)
            finished()
        }
    }

    companion object {
        const val SOCKET_NAME = "io.darkstar.darksplay.video"
        const val TAG = "DarksplayVideo"
    }
}
