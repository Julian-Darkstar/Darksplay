import io.darkstar.darksplay.AnnexBReader;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

/** No framework: exercise the actual compiled Kotlin parser on fragmented bytes. */
public final class AnnexBReaderCheck {
    static final int MAX = AnnexBReader.MAX_BYTES;
    static final int[] CHUNKS = {1, 2, 3, 4, 7, 64, 4096};
    static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    static void equal(byte[] actual, byte[] expected, String message) {
        check(Arrays.equals(actual, expected), message);
    }
    static byte[] join(byte[]... parts) {
        var out = new java.io.ByteArrayOutputStream();
        for (byte[] part : parts) out.writeBytes(part);
        return out.toByteArray();
    }
    static byte[] nal(int type, int size) {
        byte[] bytes = new byte[size + 4];
        bytes[3] = 1;
        Arrays.fill(bytes, 4, bytes.length, (byte) 0x55);
        bytes[4] = (byte) type;
        return bytes;
    }
    static InputStream fragmented(byte[] bytes, int chunk) {
        return new ByteArrayInputStream(bytes) {
            @Override public synchronized int read(byte[] b, int off, int len) {
                return super.read(b, off, Math.min(chunk, len));
            }
        };
    }
    static void fails(Runnable action, Class<? extends RuntimeException> kind, String message) {
        try {
            action.run();
        } catch (RuntimeException error) {
            check(kind.isInstance(error), "Wrong exception: " + error);
            check(error.getMessage().contains(message), "Wrong diagnostic: " + error);
            return;
        }
        throw new AssertionError("Expected rejection: " + message);
    }
    static void rejects(byte[] bytes, String message) {
        fails(() -> new AnnexBReader(new ByteArrayInputStream(bytes)).nextAccessUnit(),
            IllegalArgumentException.class, message);
    }
    static void missing(byte[] unit, int type) {
        fails(() -> AnnexBReader.Companion.parameterSet(unit, type),
            IllegalStateException.class, "SPS/PPS");
    }
    static void syntheticChecks() {
        byte[] aud = {0,0,0,1,9,0x10};
        byte[] sps = {0,0,0,1,0x67,0x42,0,0,3,0x1e};
        byte[] pps = {0,0,0,1,0x68,0x55};
        byte[] slice = {0,0,0,1,5,0x55,0,0,0};
        byte[] first = join(aud, sps, pps, nal(5, 2));
        byte[] last = join(aud, slice);
        for (int chunk : CHUNKS) {
            var reader = new AnnexBReader(fragmented(join(first, last), chunk));
            equal(reader.nextAccessUnit(), first, "Multiple NAL / 4-byte prefix chunk=" + chunk);
            equal(reader.nextAccessUnit(), last, "EOF must preserve all pending payload zeros chunk=" + chunk);
            for (int i = 0; i < 3; i++) check(reader.nextAccessUnit() == null, "Repeated EOF");
            equal(AnnexBReader.Companion.parameterSet(first, 7), sps, "Exact SPS");
            equal(AnnexBReader.Companion.parameterSet(first, 8), pps, "Exact PPS");

            // One-byte reads necessarily split every start code across read boundaries.
            byte[] three = {0,0,1,9,0x10,0,0,1,0x67,0x42,0,0,1,0x68,0x55,0,0,1,5,0x55,0,0};
            byte[] normalized = join(aud, new byte[]{0,0,0,1,0x67,0x42}, pps,
                new byte[]{0,0,0,1,5,0x55,0,0});
            var shortReader = new AnnexBReader(fragmented(three, chunk));
            byte[] unit = shortReader.nextAccessUnit();
            equal(unit, normalized, "3-byte prefixes / payload zeros / split boundaries chunk=" + chunk);
            equal(AnnexBReader.Companion.parameterSet(unit, 7), new byte[]{0,0,0,1,0x67,0x42}, "Parsed SPS");
            equal(AnnexBReader.Companion.parameterSet(unit, 8), pps, "Parsed PPS");
            check(shortReader.nextAccessUnit() == null, "3-byte EOF");
        }
        rejects(nal(5, 3), "Expected AUD");
        byte[] withoutSps = new AnnexBReader(new ByteArrayInputStream(join(aud, pps, slice))).nextAccessUnit();
        byte[] withoutPps = new AnnexBReader(new ByteArrayInputStream(join(aud, sps, slice))).nextAccessUnit();
        missing(withoutSps, 7);
        missing(withoutPps, 8);
        equal(AnnexBReader.Companion.parameterSet(withoutSps, 8), pps, "Present PPS without SPS");
        equal(AnnexBReader.Companion.parameterSet(withoutPps, 7), sps, "Present SPS without PPS");
        equal(AnnexBReader.Companion.parameterSet(join(aud, sps), 7), sps, "Parameter set at final NAL");
        for (int size = 0; size <= 4; size++) {
            missing(new byte[size], 7);
            missing(new byte[size], 8);
        }
        missing(new byte[]{0,0,0,1}, 7); // truncated prefix, no NAL header
        equal(AnnexBReader.Companion.parameterSet(new byte[]{0,0,0,1,0x67}, 7),
            new byte[]{0,0,0,1,0x67}, "Header at last valid index; no out-of-bounds access");

        rejects(join(aud, nal(5, MAX + 1)), "NAL exceeds");
        // Each NAL fits individually, but their combined AU exceeds the limit.
        rejects(join(aud, nal(7, MAX / 2), nal(5, MAX / 2)), "Access unit exceeds");
        // Regression: the EOF zero flush must enforce the combined NAL limit.
        rejects(join(aud, nal(5, MAX), new byte[]{0}), "NAL exceeds");
        byte[] exactAu = join(aud, nal(5, MAX - 10));
        equal(new AnnexBReader(new ByteArrayInputStream(exactAu)).nextAccessUnit(), exactAu,
            "Exactly MAX_BYTES AU accepted");
        System.out.println("Synthetic checks: 3/4-byte prefixes, split boundaries, multiple NAL, " +
            "EOF payload zeros, repeated EOF, AUD, SPS/PPS, bounds and NAL/AU limits passed");
    }
    public static void main(String[] args) throws Exception {
        syntheticChecks();
        byte[] source = Files.readAllBytes(Path.of(args[0]));
        int expected = Integer.parseInt(args[1]);
        for (int chunk : CHUNKS) {
            var reader = new AnnexBReader(fragmented(source, chunk));
            int count = 0;
            byte[] unit;
            while ((unit = reader.nextAccessUnit()) != null) {
                check((unit[4] & 31) == 9, "AUD missing");
                if (count == 0) {
                    check((AnnexBReader.Companion.parameterSet(unit, 7)[4] & 31) == 7, "SPS");
                    check((AnnexBReader.Companion.parameterSet(unit, 8)[4] & 31) == 8, "PPS");
                }
                count++;
            }
            check(count == expected, "Frame count with fragment=" + chunk + ": " + count);
            check(reader.nextAccessUnit() == null, "GStreamer repeated EOF");
        }
        System.out.println("Real GStreamer stream: " + expected + " AU across every fragmentation size passed");
    }
}
