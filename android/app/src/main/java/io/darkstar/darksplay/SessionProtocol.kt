package io.darkstar.darksplay

internal data class VideoConfig(val codec: String, val width: Int, val height: Int, val fps: Int) {
    val mime: String get() = "video/avc"
}

/** Small PoC state machine, independently testable without Android runtime. */
internal class SessionProtocol {
    enum class State { WAITING, CONNECTED, HELLO_OK, CONFIGURED, STREAMING, CLOSING, CLOSED }
    var state = State.WAITING
        private set
    var config: VideoConfig? = null
        private set

    @Synchronized fun connected() {
        check(state == State.WAITING) { "Unexpected connection" }
        state = State.CONNECTED
    }
    private fun integer(message: Map<String, Any>, key: String, max: Int): Int {
        val value = message[key]
        require(value is Long || value is Int) { "$key must be an integer" }
        val number = (value as Number).toLong()
        require(number in 1..max.toLong()) { "$key outside 1..$max" }
        return number.toInt()
    }
    @Synchronized fun accept(message: Map<String, Any>): Map<String, Any>? {
        val type = message["type"]
        require(type is String) { "Missing string type" }
        return when {
            state == State.CONNECTED && type == "hello" -> {
                require(message.keys == setOf("type", "protocol")) { "Unexpected HELLO fields" }
                require(integer(message, "protocol", 1) == 1) { "Incompatible protocol" }
                state = State.HELLO_OK
                mapOf("type" to "hello_ack", "protocol" to 1)
            }
            state == State.HELLO_OK && type == "video_config" -> {
                require(message.keys == setOf("type", "codec", "width", "height", "fps")) { "Unexpected config fields" }
                require(message["codec"] == "h264") { "Unsupported codec" }
                config = VideoConfig("h264", integer(message, "width", 1920),
                    integer(message, "height", 1080), integer(message, "fps", 60))
                state = State.CONFIGURED
                mapOf("type" to "video_config_ack")
            }
            state in setOf(State.CONFIGURED, State.STREAMING) && type == "goodbye" -> {
                require(message.keys == setOf("type", "reason")) { "Unexpected GOODBYE fields" }
                require(message["reason"] is String && (message["reason"] as String).length <= 128) { "Invalid reason" }
                state = State.CLOSING
                null
            }
            else -> error("Unexpected $type in $state")
        }
    }
    @Synchronized fun streaming() {
        check(state == State.CONFIGURED) { "Video before configuration" }
        state = State.STREAMING
    }
    @Synchronized fun close() { state = State.CLOSED }
}
