package io.darkstar.darksplay

import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream

/** PoC only: Annex B with one mandatory AUD per access unit, bounded memory. */
internal class AnnexBReader(input: InputStream) {
    private val input = BufferedInputStream(input, 16 * 1024)
    private var started = false
    private var eof = false
    private var pending: ByteArray? = null

    private fun nal(): ByteArray? {
        if (eof) return null
        val payload = ByteArrayOutputStream()
        var zeros = 0
        while (true) {
            val byte = input.read()
            if (byte == -1) {
                eof = true
                // No following start code: retain pending bytes of the final NAL.
                if (started) {
                    require(payload.size() + zeros <= MAX_BYTES) { "NAL exceeds PoC limit" }
                    repeat(zeros) { payload.write(0) }
                }
                return if (payload.size() == 0) null else PREFIX + payload.toByteArray()
            }
            if (byte == 0) {
                zeros++
                require(zeros <= MAX_BYTES) { "NAL exceeds PoC limit" }
                continue
            }
            if (byte == 1 && zeros >= 2) {
                zeros = 0
                if (started && payload.size() > 0) return PREFIX + payload.toByteArray()
                started = true
                continue
            }
            require(started) { "Expected Annex B start code" }
            require(payload.size() + zeros + 1 <= MAX_BYTES) { "NAL exceeds PoC limit" }
            repeat(zeros) { payload.write(0) }
            zeros = 0
            payload.write(byte)
        }
    }

    fun nextAccessUnit(): ByteArray? {
        val output = ByteArrayOutputStream()
        while (true) {
            val next = pending ?: nal()
            pending = null
            if (next == null) return if (output.size() == 0) null else output.toByteArray()
            val type = next[4].toInt() and 31
            if (type == 9 && output.size() > 0) {
                pending = next
                return output.toByteArray()
            }
            require(output.size() != 0 || type == 9) { "Expected AUD before access unit" }
            require(output.size() + next.size <= MAX_BYTES) { "Access unit exceeds PoC limit" }
            output.write(next)
        }
    }

    companion object {
        const val MAX_BYTES = 1024 * 1024
        private val PREFIX = byteArrayOf(0, 0, 0, 1)

        fun parameterSet(accessUnit: ByteArray, type: Int): ByteArray {
            for (i in 0 until accessUnit.size - 4) {
                if (accessUnit[i] == 0.toByte() && accessUnit[i + 1] == 0.toByte() &&
                    accessUnit[i + 2] == 0.toByte() && accessUnit[i + 3] == 1.toByte() &&
                    (accessUnit[i + 4].toInt() and 31) == type) {
                    var end = i + 5
                    while (end + 3 < accessUnit.size && !(accessUnit[end] == 0.toByte() &&
                        accessUnit[end + 1] == 0.toByte() && accessUnit[end + 2] == 0.toByte() &&
                        accessUnit[end + 3] == 1.toByte())) end++
                    if (end + 3 >= accessUnit.size) end = accessUnit.size
                    return accessUnit.copyOfRange(i, end)
                }
            }
            error("First access unit must contain SPS/PPS")
        }
    }
}
