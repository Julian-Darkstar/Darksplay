"""Experimental V0.1-B control plane; JSON Lines over an existing Unix socket."""
import json
import time

MAX_LINE = 4096
TIMEOUT = 5.0
VIDEO_CONFIG = {"type": "video_config", "codec": "h264", "width": 1280, "height": 720, "fps": 30}


class ProtocolError(RuntimeError):
    pass


class TransportClosed(RuntimeError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate JSON key")
        result[key] = value
    return result


class Control:
    def __init__(self, stream, timeout=TIMEOUT):
        self.stream = stream
        self.timeout = timeout
        self.state = "CONNECTED"

    def send(self, message):
        data = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(data) > MAX_LINE:
            raise ProtocolError("control line too large")
        self.stream.settimeout(self.timeout)
        self.stream.sendall(data + b"\n")
        print("control TX " + data.decode(), flush=True)

    def read(self):
        line = bytearray()
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("control message/ACK timeout")
            self.stream.settimeout(remaining)
            byte = self.stream.recv(1)
            if not byte:
                raise TransportClosed("control EOF" + (" inside line" if line else ""))
            if byte == b"\n":
                break
            if len(line) == MAX_LINE:
                raise ProtocolError("control line too large")
            line += byte
        try:
            value = json.loads(line.decode("utf-8"), object_pairs_hook=unique_object,
                               parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError("invalid number")))
        except (ValueError, UnicodeError) as error:
            raise ProtocolError("invalid JSON/UTF-8") from error
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise ProtocolError("control object requires string type")
        print("control RX " + str(value), flush=True)
        return value

    def handshake(self):
        if self.state != "CONNECTED":
            raise ProtocolError("HELLO in unexpected state")
        self.send({"type": "hello", "protocol": 1})
        ack = self.read()
        if ack != {"type": "hello_ack", "protocol": 1} or type(ack.get("protocol")) is not int:
            raise ProtocolError("expected HELLO_ACK protocol 1")
        self.state = "HELLO_OK"
        self.send(VIDEO_CONFIG)
        if self.read() != {"type": "video_config_ack"}:
            raise ProtocolError("expected VIDEO_CONFIG_ACK")
        self.state = "CONFIGURED"

    def begin_video(self, start_video):
        # The callback cannot run when either ACK is missing, malformed or late.
        self.handshake()
        if self.state != "CONFIGURED":
            raise ProtocolError("video before configuration ACK")
        self.state = "STREAMING"
        return start_video()

    def goodbye(self, reason):
        self.send({"type": "goodbye", "reason": reason})
        self.state = "CLOSING"

    def close(self):
        self.state = "CLOSED"
        self.stream.close()
