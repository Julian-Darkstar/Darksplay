package io.darkstar.darksplay

import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** UI wake-up with bounded transport checks; no protocol bytes are read here. */
internal class StartGate {
    private val wake = CountDownLatch(1)
    fun release() = wake.countDown()
    fun awaitStart(checkPeer: () -> Unit) {
        while (!wake.await(50, TimeUnit.MILLISECONDS)) checkPeer()
    }
}
