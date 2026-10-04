#!/usr/bin/env python3
"""V0.2 session: PipeWire ScreenCast -> GStreamer -> AF_UNIX -> ADB/physical USB -> Android.

Replaces the synthetic videotestsrc source with real screen capture from
xdg-desktop-portal ScreenCast over PipeWire. Preserves V0.1-B session control
and protocol (HELLO -> HELLO_ACK -> VIDEO_CONFIG -> VIDEO_CONFIG_ACK).
"""
import argparse
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import tempfile
import threading
import time

from screencast_portal import PortalCancelled, PortalError, PortalScreenCast
from session_control import Control, ProtocolError, TransportClosed

ROOT = Path(__file__).resolve().parent.parent

ELEMENTS_SYNTHETIC = ("videotestsrc", "videoconvert", "openh264enc", "h264parse", "fdsink")
ELEMENTS_PIPEWIRE = (
    "pipewiresrc",
    "videorate",
    "videoconvert",
    "videoscale",
    "openh264enc",
    "h264parse",
    "fdsink",
)


def classify_pipeline_exit(result, stream, source_revoked=False):
    """SIGPIPE alone is not evidence of an expected receiver closure."""
    if result == 0:
        print("PoC outcome=completed; pipeline finished normally", flush=True)
        return 0
    if source_revoked:
        print("PoC outcome=source_revoked; portal closed the capture session; "
              f"GStreamer exit={result} is expected", flush=True)
        return 2
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


def pipeline_args_synthetic(fd, seconds=0):
    """Synthetic videotestsrc pipeline preserved for regression testing."""
    pipeline = ["gst-launch-1.0", "-e", "-v", "videotestsrc", "is-live=true", "pattern=ball"]
    if seconds:
        pipeline.append(f"num-buffers={seconds * 30}")
    pipeline += [
        "!", "video/x-raw,width=1280,height=720,framerate=30/1",
        "!", "videoconvert", "!", "video/x-raw,format=I420",
        "!", "openh264enc", "bitrate=4000000", "rate-control=bitrate",
        "gop-size=30", "complexity=low", "enable-frame-skip=false",
        "!", "h264parse", "config-interval=-1",
        "!", "video/x-h264,stream-format=byte-stream,alignment=au,profile=constrained-baseline",
        "!", "fdsink", f"fd={fd}", "sync=false",
    ]
    return pipeline


# Backward compatibility alias
pipeline_args = pipeline_args_synthetic


def pipeline_args_pipewire(video_fd, pw_fd, node_id, seconds=0, keepalive_ms=1000):
    """PipeWire screen capture pipeline.

    Captures from pipewiresrc via portal FD and node ID, adjusts rate to 30 FPS,
    scales and letterboxes/pillarboxes preserving aspect ratio to 1280x720, converts
    to I420, encodes with OpenH264 constrained baseline, and outputs to video_fd.
    """
    pipeline = [
        "gst-launch-1.0", "-e", "-v",
        "pipewiresrc",
        f"fd={pw_fd}",
        f"path={node_id}",
        "do-timestamp=true",
        f"keepalive-time={keepalive_ms}",
    ]
    if seconds:
        pipeline.append(f"num-buffers={seconds * 30}")
    pipeline += [
        "!", "videorate",
        "!", "video/x-raw,framerate=30/1",
        "!", "videoconvert",
        "!", "videoscale", "add-borders=true",
        "!", "video/x-raw,width=1280,height=720,pixel-aspect-ratio=1/1",
        "!", "videoconvert",
        "!", "video/x-raw,format=I420",
        "!", "openh264enc", "bitrate=4000000", "rate-control=bitrate",
        "gop-size=30", "complexity=low", "enable-frame-skip=false",
        "!", "h264parse", "config-interval=-1",
        "!", "video/x-h264,stream-format=byte-stream,alignment=au,profile=constrained-baseline",
        "!", "fdsink", f"fd={video_fd}", "sync=false",
    ]
    return pipeline


pipewire_pipeline_args = pipeline_args_pipewire


def reap(process):
    if process.poll() is None:
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


def best_effort_goodbye(control, reason):
    try:
        control.goodbye(reason)
    except (OSError, RuntimeError) as error:
        print(f"GOODBYE unavailable: {error}", flush=True)


def run_session(control, open_video, start_pipeline, source_revoked=None):
    """Injectable boundaries let tests prove no video/process starts without both ACKs."""
    def stream_video():
        with open_video() as stream:
            process = None
            try:
                process = start_pipeline(stream)
                beginning = time.monotonic()
                control_closed = False
                while process.poll() is None:
                    if source_revoked is not None and source_revoked.is_set():
                        reap(process)
                        # V0.1-B has no source_revoked reason; this is the existing
                        # wire reason for an expected transport interruption.
                        best_effort_goodbye(control, "transport_closed")
                        print("PoC outcome=source_revoked; capture session closed", flush=True)
                        return 2
                    readable, _, _ = select.select([control.stream], [], [], 0.1)
                    if readable:
                        try:
                            message = control.read()
                        except TransportClosed:
                            control_closed = True
                            break
                        raise ProtocolError(f"unexpected control message while streaming: {message}")
                if control_closed:
                    reap(process)
                    # Control loss must not hide an unrelated pipeline error racing EOF.
                    if process.returncode not in (0, -signal.SIGPIPE, -signal.SIGINT,
                                                  -signal.SIGTERM, -signal.SIGKILL):
                        raise RuntimeError(f"unexpected GStreamer failure (exit={process.returncode}) alongside control EOF")
                    print(f"GStreamer exit={process.returncode}; control EOF; "
                          "PoC outcome=transport_closed", flush=True)
                    return 2
                result = process.wait()
                print(f"GStreamer exit={result}; duration={time.monotonic() - beginning:.3f}s", flush=True)
                # Session.Closed and the PipeWire error can be delivered in either order.
                if source_revoked is not None:
                    source_revoked.wait(0.2)
                outcome = classify_pipeline_exit(
                    result,
                    stream,
                    source_revoked=source_revoked is not None and source_revoked.is_set(),
                )
                if outcome == 0:
                    stream.shutdown(socket.SHUT_WR)  # deliver video EOF before GOODBYE
                    control.goodbye("completed")
                    try:
                        message = control.read()
                    except TransportClosed:
                        print("Session completed; Android closed control after GOODBYE", flush=True)
                    else:
                        raise ProtocolError(f"unexpected response after GOODBYE: {message}")
                else:
                    best_effort_goodbye(control, "transport_closed")
                return outcome
            finally:
                if process is not None:
                    reap(process)
    try:
        return control.begin_video(stream_video)
    except BaseException:
        best_effort_goodbye(control, "interrupted")
        raise
    finally:
        control.close()


def _run_forwarded_session(adb, serial, args, make_pipeline, source_revoked=None):
    directory = ROOT / "build" / "video-poc"
    directory.mkdir(parents=True, exist_ok=True)
    forwards = []
    with tempfile.TemporaryDirectory(prefix="session-", dir=directory) as temporary:
        paths = {name: str(Path(temporary) / (name + ".sock")) for name in ("control", "video")}
        if any(len(os.fsencode(path)) >= 104 for path in paths.values()):
            raise RuntimeError("project path is too long for a Unix socket")
        try:
            for name, path in paths.items():
                local = "localfilesystem:" + path
                remote = "localabstract:io.darkstar.darksplay." + name
                subprocess.run(adb + ["forward", "--no-rebind", local, remote], check=True)
                forwards.append(local)

            def connect(name):
                stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    stream.settimeout(5)
                    stream.connect(paths[name])
                    stream.settimeout(None)
                    return stream
                except BaseException:
                    stream.close()
                    raise

            print(f"USB serial={serial}; explicit Android receiver required", flush=True)
            return run_session(
                Control(connect("control")),
                lambda: connect("video"),
                make_pipeline,
                source_revoked=source_revoked,
            )
        finally:
            for local in reversed(forwards):
                subprocess.run(adb + ["forward", "--remove", local], check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="authorized physical USB serial; otherwise require exactly one")
    parser.add_argument("--seconds", type=int, default=0, help="finite test duration; 0 runs until Ctrl-C")
    parser.add_argument(
        "--videotestsrc",
        action="store_true",
        help="use synthetic videotestsrc instead of PipeWire capture (diagnostic/regression)",
    )
    parser.add_argument(
        "--keepalive-ms",
        type=int,
        default=1000,
        help="pipewiresrc keepalive-time in milliseconds (default: 1000)",
    )
    args = parser.parse_args()
    if args.seconds < 0:
        parser.error("--seconds must be nonnegative")
    if args.keepalive_ms < 0:
        parser.error("--keepalive-ms must be nonnegative")
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

    elements_to_check = ELEMENTS_SYNTHETIC if args.videotestsrc else ELEMENTS_PIPEWIRE
    for element in elements_to_check:
        subprocess.run(["gst-inspect-1.0", element], check=True, stdout=subprocess.DEVNULL)

    if args.videotestsrc:
        print("Using synthetic source: videotestsrc", flush=True)
        def start_synthetic(stream):
            pipeline = pipeline_args_synthetic(stream.fileno(), args.seconds)
            print("Pipeline: " + " ".join(pipeline), flush=True)
            return subprocess.Popen(pipeline, pass_fds=(stream.fileno(),))
        return _run_forwarded_session(adb, serial, args, start_synthetic)

    # V0.2: PipeWire capture via xdg-desktop-portal ScreenCast.
    # Invariant: Screen selection consent occurs BEFORE Darksplay timeouts begin.
    print("Requesting screen capture via xdg-desktop-portal ScreenCast...", flush=True)
    source_revoked = threading.Event()
    try:
        with PortalScreenCast(on_closed=source_revoked.set) as portal:
            portal.start_dispatch()
            print(
                f"Screen capture authorized (node_id={portal.node_id}, fd={portal.pipewire_fd})",
                flush=True,
            )

            def start_pipewire(stream):
                pipeline = pipeline_args_pipewire(
                    stream.fileno(),
                    portal.pipewire_fd,
                    portal.node_id,
                    args.seconds,
                    args.keepalive_ms,
                )
                print("Pipeline: " + " ".join(pipeline), flush=True)
                return subprocess.Popen(
                    pipeline,
                    pass_fds=(stream.fileno(), portal.pipewire_fd),
                )

            try:
                return _run_forwarded_session(
                    adb, serial, args, start_pipewire,
                    source_revoked=source_revoked,
                )
            finally:
                portal.stop_dispatch()

    except PortalCancelled:
        print("Screen selection cancelled by user in GNOME dialog; exiting cleanly", flush=True)
        return 0


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
