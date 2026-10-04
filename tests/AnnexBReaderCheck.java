import io.darkstar.darksplay.AnnexBReader;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

/** No framework: exercise the actual compiled Kotlin parser on fragmented bytes. */
public final class AnnexBReaderCheck {
    static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
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
    static void rejects(byte[] bytes) throws Exception {
        try {
            new AnnexBReader(new ByteArrayInputStream(bytes)).nextAccessUnit();
            throw new AssertionError("Malformed stream accepted");
        } catch (IllegalArgumentException expected) { }
    }
    public static void main(String[] args) throws Exception {
        byte[] source = Files.readAllBytes(Path.of(args[0]));
        int expected = Integer.parseInt(args[1]);
        for (int chunk : new int[] {1, 2, 3, 7, 64, 4096}) {
            InputStream fragmented = new ByteArrayInputStream(source) {
                @Override public synchronized int read(byte[] b, int off, int len) {
                    return super.read(b, off, Math.min(chunk, len));
                }
            };
            var reader = new AnnexBReader(fragmented);
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
        }
        rejects(nal(5, 3)); // missing AUD
        rejects(join(nal(9, 2), nal(5, 1024 * 1024))); // bounded NAL/AU
        var threeByte = new AnnexBReader(new ByteArrayInputStream(
            new byte[] {0,0,1,9,0x10,0,0,1,5,0x55}));
        check(threeByte.nextAccessUnit().length == 12, "3-byte start codes / EOF");
        check(threeByte.nextAccessUnit() == null, "Repeated EOF");
        System.out.println("AnnexBReader: fragmented stream, SPS/PPS, EOF and limits passed");
    }
}
