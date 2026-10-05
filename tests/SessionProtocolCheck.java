import io.darkstar.darksplay.SessionProtocol;
import io.darkstar.darksplay.ControlLines;
import java.io.*;
import java.net.SocketTimeoutException;
import java.util.*;

/** Actual Kotlin state machine and bounded UTF-8 framing; no second implementation. */
public class SessionProtocolCheck {
    interface Action { void run() throws Exception; }
    static void check(boolean value) { if (!value) throw new AssertionError(); }
    static void fails(Action action) throws Exception {
        try { action.run(); } catch (Exception expected) { return; }
        throw new AssertionError("Invalid input accepted");
    }
    static Map<String,Object> hello(int version) { return Map.of("type","hello_ack","protocol",version); }
    static Map<String,Object> config() {
        return Map.of("type","video_config","codec","h264","width",1280,"height",720,"fps",30);
    }
    static SessionProtocol connected() { var p=new SessionProtocol(); p.requestStart(); p.connected(); check(p.hello().equals(Map.of("type","hello","protocol",1))); return p; }
    public static void main(String[] args) throws Exception {
        var idle = new SessionProtocol(); idle.connected();
        fails(() -> idle.hello());
        fails(() -> idle.accept(hello(1)));
        fails(() -> connected().accept(Map.of("type","hello","protocol",1)));
        var p=connected();
        check(p.accept(hello(1)) == null);
        check(p.accept(config()).equals(Map.of("type","video_config_ack")));
        check(p.getConfig().getWidth()==1280 && p.getConfig().getHeight()==720 && p.getConfig().getFps()==30);
        check(p.getConfig().getMime().equals("video/avc"));
        var alternative=connected(); alternative.accept(hello(1));
        alternative.accept(Map.of("type","video_config","codec","h264","width",640,"height",480,"fps",24));
        check(alternative.getConfig().getWidth()==640 && alternative.getConfig().getHeight()==480 && alternative.getConfig().getFps()==24);
        fails(() -> p.streaming());
        var order = new ArrayList<String>();
        p.startVideo(() -> { order.add("prepare"); return kotlin.Unit.INSTANCE; },
            () -> { order.add("ack"); return kotlin.Unit.INSTANCE; },
            () -> { order.add("start"); return kotlin.Unit.INSTANCE; });
        check(order.equals(List.of("prepare", "ack", "start")));
        p.streaming();
        var broken = connected(); broken.accept(hello(1)); broken.accept(config());
        var blocked = new ArrayList<String>();
        fails(() -> broken.startVideo(() -> { blocked.add("prepare"); return kotlin.Unit.INSTANCE; },
            () -> { throw new IllegalStateException("ACK write failed"); },
            () -> { blocked.add("start"); return kotlin.Unit.INSTANCE; }));
        check(blocked.equals(List.of("prepare")));
        fails(() -> broken.streaming());
        fails(() -> p.accept(hello(1)));
        check(p.accept(Map.of("type","goodbye","reason","completed"))==null);
        fails(() -> p.accept(config()));
        p.close(); check(p.getState()==SessionProtocol.State.CLOSED);
        fails(() -> p.accept(hello(1)));
        fails(() -> connected().accept(hello(2)));
        fails(() -> connected().accept(Map.of()));
        fails(() -> connected().accept(config()));
        fails(() -> connected().accept(Map.of("type","ping")));
        fails(() -> connected().streaming());
        for (String field : List.of("codec","width","height","fps")) {
            for (Object invalid : field.equals("codec") ? List.of("av1",1) : List.of(0,-1,100000,"30",true)) {
                var q=connected(); q.accept(hello(1));
                var data=new HashMap<>(config()); data.put(field,invalid);
                fails(() -> q.accept(data));
                q.close(); check(q.getState()==SessionProtocol.State.CLOSED);
            }
        }
        for (int chunk : List.of(1,2,7,64)) {
            var input=new ByteArrayInputStream("{\"type\":\"hello\",\"protocol\":1}\n".getBytes()) {
                @Override public synchronized int read(byte[] b,int off,int len) {return super.read(b,off,Math.min(chunk,len));}
            };
            check(ControlLines.INSTANCE.read(input,5000L,()->false).contains("hello"));
        }
        fails(() -> ControlLines.INSTANCE.read(new ByteArrayInputStream(new byte[4097]),5000L,()->false));
        fails(() -> ControlLines.INSTANCE.read(new ByteArrayInputStream("partial".getBytes()),5000L,()->false));
        fails(() -> ControlLines.INSTANCE.read(new ByteArrayInputStream(new byte[]{(byte)0xff,10}),5000L,()->false));
        InputStream timed=new InputStream() {public int read() throws IOException {throw new SocketTimeoutException();}};
        fails(() -> ControlLines.INSTANCE.read(timed,10L,()->false));
        System.out.println("Kotlin session/state/config/UTF-8/size/EOF/timeout checks passed");
    }
}
