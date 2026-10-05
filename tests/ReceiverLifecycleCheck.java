import io.darkstar.darksplay.ReceiverLifecycle;
import io.darkstar.darksplay.SessionProtocol;
import io.darkstar.darksplay.StartGate;
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Production Kotlin gate/ownership, with a real local Unix peer; no Android framework. */
public class ReceiverLifecycleCheck {
    static void check(boolean value) { if (!value) throw new AssertionError(); }

    static void peerWait(String action) throws Exception {
        var directory = Files.createTempDirectory("darksplay-lifecycle-");
        var path = directory.resolve("control.sock");
        var gate = new StartGate();
        var prepared = new CountDownLatch(1);
        var checked = new CountDownLatch(1);
        var cleaned = new AtomicBoolean();
        var hello = new AtomicBoolean();
        var video = new AtomicBoolean();
        var stopping = new AtomicBoolean();
        var failure = new AtomicReference<Throwable>();
        var protocol = new SessionProtocol();
        try (var listener = ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            listener.bind(UnixDomainSocketAddress.of(path));
            try (var peer = SocketChannel.open(UnixDomainSocketAddress.of(path));
                 var accepted = listener.accept()) {
                listener.close();
                accepted.configureBlocking(false);
                protocol.connected();
                var worker = new Thread(() -> {
                    try (accepted) {
                        prepared.countDown();
                        gate.awaitStart(() -> {
                            try {
                                // JVM socket adapter for the same peer-health seam used by Android.
                                int count = accepted.read(ByteBuffer.allocate(1));
                                if (count < 0) throw new UncheckedIOException(new EOFException("Control EOF before Start"));
                                if (count > 0) throw new IllegalStateException("Unexpected pre-Start data");
                                checked.countDown();
                                return kotlin.Unit.INSTANCE;
                            } catch (IOException error) { throw new UncheckedIOException(error); }
                        });
                        if (stopping.get()) return;
                        check(protocol.hello().get("type").equals("hello"));
                        hello.set(true);
                        // No configuration ACK: video must remain unauthorized.
                        try { protocol.streaming(); video.set(true); }
                        catch (IllegalStateException expected) { }
                    } catch (Throwable error) { failure.set(error); }
                    finally { protocol.close(); cleaned.set(true); }
                });
                worker.start();
                try {
                    check(prepared.await(1, TimeUnit.SECONDS));
                    check(checked.await(1, TimeUnit.SECONDS));
                    check(worker.isAlive() && !hello.get() && !video.get());
                    if (action.equals("EOF")) peer.shutdownOutput();
                    else if (action.equals("close")) peer.close();
                    else if (action.equals("Stop")) { stopping.set(true); gate.release(); }
                    else { protocol.requestStart(); gate.release(); }
                    worker.join(2000);
                    check(!worker.isAlive() && cleaned.get() && !accepted.isOpen());
                    check(protocol.getState() == SessionProtocol.State.CLOSED);
                    check(!video.get());
                    check(hello.get() == action.equals("Start"));
                    if (action.equals("EOF") || action.equals("close")) {
                        check(failure.get() instanceof UncheckedIOException);
                        check(failure.get().getCause() instanceof EOFException);
                    } else check(failure.get() == null);
                } finally {
                    stopping.set(true); gate.release(); worker.join(2000);
                }
            }
        } finally { Files.deleteIfExists(path); Files.deleteIfExists(directory); }
        System.out.println("pre-Start " + action + ": cleanup, HELLO/video gates OK");
    }

    static void surfaceRecreation() {
        var lifecycle = new ReceiverLifecycle<Object>();
        Object old = new Object(), next = new Object();
        lifecycle.setAvailable(true);
        lifecycle.attach(old);
        check(!lifecycle.getCanStart());
        lifecycle.prepared(old);
        check(lifecycle.getCanStart());
        check(lifecycle.start() == old);
        lifecycle.setAvailable(false); // surfaceDestroyed / onStop
        check(lifecycle.stop() == old);
        lifecycle.setAvailable(true); // new Surface before old cleanup callback
        lifecycle.prepared(old); // a late callback cannot revive a closing receiver
        check(!lifecycle.getCanStart() && !lifecycle.getCanPrepare());
        check(lifecycle.start() == null);
        check(lifecycle.getReceiver() == old);
        check(lifecycle.finished(old));
        check(lifecycle.getCanPrepare() && !lifecycle.getCanStart());
        lifecycle.attach(next);
        check(!lifecycle.getCanStart());
        check(!lifecycle.finished(old)); // stale callback cannot clear replacement
        lifecycle.prepared(old);
        check(!lifecycle.getCanStart());
        lifecycle.prepared(next);
        check(lifecycle.getCanStart());
        check(lifecycle.start() == next);
        lifecycle.setAvailable(false);
        lifecycle.stop(); lifecycle.finished(next);
        check(!lifecycle.getCanPrepare() && !lifecycle.getCanStart());
        System.out.println("Surface recreation during close: ownership/Start gates OK");
    }

    public static void main(String[] args) throws Exception {
        peerWait("EOF"); peerWait("close"); peerWait("Stop"); peerWait("Start");
        surfaceRecreation();
    }
}
