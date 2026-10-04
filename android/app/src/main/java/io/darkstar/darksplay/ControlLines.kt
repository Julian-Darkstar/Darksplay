package io.darkstar.darksplay

import java.io.ByteArrayOutputStream
import java.io.EOFException
import java.io.InputStream
import java.net.SocketTimeoutException
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction

internal object ControlLines {
    const val MAX_BYTES = 4096
    // Input must provide short SocketTimeoutException ticks (Android uses Unix poll).
    fun read(input: InputStream, timeoutMs: Long = 5000, idleAllowed: () -> Boolean = { false }): String {
        val bytes = ByteArrayOutputStream()
        var deadline = System.nanoTime() + timeoutMs * 1_000_000
        while (true) {
            val value = try { input.read() } catch (error: SocketTimeoutException) {
                if (bytes.size() == 0 && idleAllowed()) {
                    deadline = System.nanoTime() + timeoutMs * 1_000_000
                    continue
                }
                if (System.nanoTime() >= deadline) throw SocketTimeoutException("Control message timeout")
                continue
            }
            if (value == -1) throw EOFException("Control EOF")
            if (value == 10) break
            require(bytes.size() < MAX_BYTES) { "Control line exceeds $MAX_BYTES bytes" }
            bytes.write(value)
            if (System.nanoTime() >= deadline) throw SocketTimeoutException("Control message timeout")
        }
        return Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes.toByteArray())).toString()
    }
}
