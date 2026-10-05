package io.darkstar.darksplay

import android.net.LocalServerSocket
import android.net.LocalSocket
import android.system.Os
import android.system.OsConstants
import android.system.StructPollfd
import java.io.InputStream
import java.io.EOFException
import java.net.SocketTimeoutException
import android.util.Log
import android.view.Surface
import org.json.JSONObject

/** Owns exactly one control connection and its newly created video receiver. */
internal class SessionReceiver(private val surface: Surface, private val report: (String) -> Unit,
    private val prepared: () -> Unit,
    private val finished: () -> Unit) {
    private val lock = Any()
    @Volatile private var stopping = false
    private var listener: LocalServerSocket? = null
    private var control: LocalSocket? = null
    private var video: VideoReceiver? = null
    private val protocol = SessionProtocol()

    private val startGate = StartGate()
    fun prepare() { Thread({ runSession() }, "DarksplayControl").start() }
    fun start() = synchronized(lock) {
        // Peer loss can race a queued UI action. Never start a closing receiver.
        if (!stopping) {
            protocol.requestStart()
            startGate.release()
        }
    }
    fun stop() {
        synchronized(lock) {
            stopping = true
            startGate.release()
            video?.stop()
            runCatching { control?.shutdownInput() }
            runCatching { control?.close() }
            runCatching { listener?.let { Os.shutdown(it.fileDescriptor, OsConstants.SHUT_RDWR) } }
            runCatching { listener?.close() }
        }
    }
    private fun runSession() {
        var reason = "Stream finished"
        try {
            synchronized(lock) {
                if (stopping) return
                listener = LocalServerSocket(CONTROL_NAME)
            }
            report("Control prepared / Press Start")
            Log.i(TAG, "state=WAITING; control endpoint prepared; video endpoint absent")
            prepared()
            val accepted = listener!!.accept()
            synchronized(lock) {
                if (stopping) { accepted.close(); return }
                control = accepted
                listener?.close()
                listener = null
            }
            accepted.soTimeout = 0
            protocol.connected()
            report("Host connected / Press Start")
            startGate.awaitStart {
                val poll = StructPollfd().apply {
                    fd = accepted.fileDescriptor
                    events = OsConstants.POLLIN.toShort()
                }
                Os.poll(arrayOf(poll), 0)
                val events = poll.revents.toInt()
                if (events and (OsConstants.POLLHUP or OsConstants.POLLERR or OsConstants.POLLNVAL) != 0)
                    throw EOFException("Control closed before Start")
                if (events and OsConstants.POLLIN != 0) {
                    // Sole reader: after POLLIN, peek cannot lose data to another reader.
                    // Distinguish half-close/EOF without consuming protocol bytes.
                    val count = Os.recvfrom(accepted.fileDescriptor, ByteArray(1), 0, 1,
                        OsConstants.MSG_PEEK, null)
                    if (count == 0) throw EOFException("Control EOF before Start")
                    error("Unexpected control data before Start")
                }
            }
            if (stopping) return
            report("Negotiating")
            Log.i(TAG, "state=${protocol.state}")
            val input = object : InputStream() {
                override fun read(): Int {
                    val poll = StructPollfd().apply {
                        fd = accepted.fileDescriptor
                        events = OsConstants.POLLIN.toShort()
                    }
                    if (Os.poll(arrayOf(poll), 250) == 0) throw SocketTimeoutException("Control poll")
                    return accepted.inputStream.read()
                }
            }
            val output = accepted.outputStream
            fun receive(idleAllowed: () -> Boolean = { false }): Map<String, Any> {
                val message = ControlJson.parse(ControlLines.read(input, idleAllowed = idleAllowed))
                Log.i(TAG, "control RX $message")
                return message
            }
            fun send(message: Map<String, Any>) {
                val bytes = (JSONObject(message).toString() + "\n").toByteArray(Charsets.UTF_8)
                require(bytes.size <= ControlLines.MAX_BYTES + 1)
                output.write(bytes)
                output.flush()
                Log.i(TAG, "control TX $message; state=${protocol.state}")
            }
            send(protocol.hello())
            protocol.accept(receive()) // Must be HELLO_ACK before VIDEO_CONFIG.
            val ack = protocol.accept(receive()) ?: error("Missing VIDEO_CONFIG_ACK")
            val config = protocol.config ?: error("No video configuration")
            val receiver = VideoReceiver(surface, config,
                { text -> Log.i(TAG, text) },
                {
                    protocol.streaming()
                    report("Streaming: ${config.codec} / ${config.width}×${config.height} / ${config.fps} FPS")
                    Log.i(TAG, "state=${protocol.state}; config=$config")
                }, { Log.i(TAG, "video worker finished") })
            synchronized(lock) {
                if (stopping) return
                video = receiver
                report("Configured: ${config.codec} / ${config.width}×${config.height} / ${config.fps} FPS")
                protocol.startVideo({ receiver.prepare() }, { send(ack) }, { receiver.start() })
            }
            val goodbye = receive { !stopping && receiver.isAlive() }
            protocol.accept(goodbye) // only GOODBYE is legal here
            Log.i(TAG, "GOODBYE accepted: ${goodbye["reason"]}")
            receiver.awaitTermination() // allow final AU and EOS to drain normally
        } catch (error: Exception) {
            if (!stopping) {
                reason = "Session error: ${error.message}"
                Log.e(TAG, "session error; state=${protocol.state}", error)
            }
        } finally {
            stop()
            video?.awaitTermination()
            protocol.close()
            synchronized(lock) {
                control = null
                listener = null
                video = null
            }
            Log.i(TAG, "state=CLOSED; control/video resources released")
            report(if (reason == "Stream finished") "Stream finished" else reason)
            finished()
        }
    }
    companion object {
        const val CONTROL_NAME = "io.darkstar.darksplay.control"
        const val TAG = "DarksplaySession"
    }
}
