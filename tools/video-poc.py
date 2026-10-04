#!/usr/bin/env python3
"""V0.1-A only: GStreamer -> AF_UNIX -> ADB/physical USB -> Android."""
import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
REMOTE = "localabstract:io.darkstar.darksplay.video"


def classify_pipeline_exit(result, stream):
    """SIGPIPE alone is not evidence of an expected receiver closure."""
    if result == 0:
        print("PoC outcome=completed; pipeline finished normally", flush=True)
        return 0
    if result == -signal.SIGPIPE:
        try:
            closed = stream.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b""
        except ConnectionResetError:
            closed = True
        except (BlockingIOError, OSError) as error:
            closed = False
            print(f"SIGPIPE peer-close check: {error}", flush=True)
        if closed:
            print("PoC outcome=transport_closed; receiver/ADB endpoint closed "
                  "and GStreamer received SIGPIPE; exact reason unknown", flush=True)
            return 2  # distinguish interruption from completion and pipeline failure
    raise RuntimeError(f"unexpected GStreamer failure (exit={result}); inspect GStreamer and logcat")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="authorized physical USB serial; otherwise require exactly one")
    parser.add_argument("--seconds", type=int, default=0, help="finite test duration; 0 runs until Ctrl-C")
    args = parser.parse_args()
    if args.seconds < 0:
        parser.error("--seconds must be nonnegative")
    if os.environ.get("ADB_SERVER_SOCKET"):
        parser.error("ADB_SERVER_SOCKET must be unset; use the local ADB server")
    devices = subprocess.check_output(["adb", "devices", "-l"], text=True)
    usb = [line.split()[0] for line in devices.splitlines()
           if len(line.split()) >= 2 and line.split()[1] == "device" and "usb:" in line]
    if args.serial:
        if args.serial not in usb:
            parser.error("selected serial is not an authorized physical USB device")
        serial = args.serial
    elif len(usb) == 1:
        serial = usb[0]
    else:
        parser.error("require exactly one authorized USB device or --serial")
    adb = ["adb", "-s", serial]
    for element in ("videotestsrc", "videoconvert", "openh264enc", "h264parse", "fdsink"):
        subprocess.run(["gst-inspect-1.0", element], check=True, stdout=subprocess.DEVNULL)
    directory = ROOT / "build" / "video-poc"
    directory.mkdir(parents=True, exist_ok=True)
    process = None
    forwarded = False
    with tempfile.TemporaryDirectory(prefix="session-", dir=directory) as temporary:
        address = str(Path(temporary) / "video.sock")
        if len(os.fsencode(address)) >= 104:
            parser.error("project path is too long for a Unix socket; use a shorter checkout path")
        local = "localfilesystem:" + address
        try:
            subprocess.run(adb + ["forward", "--no-rebind", local, REMOTE], check=True)
            forwarded = True
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                stream.settimeout(5)
                stream.connect(address)
                stream.settimeout(None)
                pipeline = ["gst-launch-1.0", "-e", "-v", "videotestsrc", "is-live=true", "pattern=ball"]
                if args.seconds:
                    pipeline.append(f"num-buffers={args.seconds * 30}")
                pipeline += ["!", "video/x-raw,width=1280,height=720,framerate=30/1",
                             "!", "videoconvert", "!", "video/x-raw,format=I420",
                             "!", "openh264enc", "bitrate=4000000", "rate-control=bitrate",
                             "gop-size=30", "complexity=low", "enable-frame-skip=false",
                             "!", "h264parse", "config-interval=-1",
                             "!", "video/x-h264,stream-format=byte-stream,alignment=au,profile=constrained-baseline",
                             "!", "fdsink", f"fd={stream.fileno()}", "sync=false"]
                print(f"USB serial={serial}; receiver must already be explicitly started", flush=True)
                print("Pipeline: " + " ".join(pipeline), flush=True)
                beginning = time.monotonic()
                process = subprocess.Popen(pipeline, pass_fds=(stream.fileno(),))
                result = process.wait()
                print(f"GStreamer exit={result}; duration={time.monotonic() - beginning:.3f}s", flush=True)
                return classify_pipeline_exit(result, stream)
        finally:
            if process is not None and process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            if forwarded:
                subprocess.run(adb + ["forward", "--remove", local], check=False)


def interrupted(*_):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("PoC stopped; resources cleaned up")
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(f"PoC error: {error}")
