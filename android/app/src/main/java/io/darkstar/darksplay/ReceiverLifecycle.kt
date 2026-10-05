package io.darkstar.darksplay

/** Activity-thread ownership. A replacement cannot overlap the closing receiver. */
internal class ReceiverLifecycle<T : Any> {
    enum class Phase { EMPTY, PREPARING, READY, STARTED, CLOSING }
    var receiver: T? = null
        private set
    var phase = Phase.EMPTY
        private set
    var available = false
    val canPrepare: Boolean get() = available && receiver == null
    val canStart: Boolean get() = available && phase == Phase.READY

    fun attach(value: T) {
        check(canPrepare)
        receiver = value
        phase = Phase.PREPARING
    }
    fun prepared(value: T) {
        if (receiver === value && phase == Phase.PREPARING) phase = Phase.READY
    }
    fun start(): T? {
        if (!canStart) return null
        phase = Phase.STARTED
        return receiver
    }
    fun stop(): T? {
        if (receiver != null) phase = Phase.CLOSING
        return receiver
    }
    fun finished(value: T): Boolean {
        if (receiver !== value) return false
        receiver = null
        phase = Phase.EMPTY
        return true
    }
}
