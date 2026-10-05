"""Actual sender and NDJSON transport over AF_UNIX, no Android or new packages."""
import importlib.util
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from session_control import Control, ProtocolError, TransportClosed, MAX_LINE, VIDEO_CONFIG
spec = importlib.util.spec_from_file_location("video_poc", Path(__file__).parents[1] / "tools/video-poc.py")
poc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)


class ControlChecks(unittest.TestCase):
    def setUp(self):
        self.host, self.peer = socket.socketpair(socket.AF_UNIX)
        self.addCleanup(self.host.close)
        self.addCleanup(self.peer.close)
        self.control = Control(self.host, timeout=0.03)

    def test_initial_wait_sends_nothing_and_hello_starts_negotiation(self):
        import json
        outcome = []
        prepare = Mock(return_value=42)
        worker = threading.Thread(target=lambda: outcome.append(self.control.begin_video(prepare)))
        worker.start()
        self.peer.settimeout(0.1)  # Longer than the handshake timeout: idle wait is intentional.
        with self.assertRaises(TimeoutError):
            self.peer.recv(1)
        self.assertTrue(worker.is_alive())
        self.peer.sendall(b'{"type":"hello","protocol":1}\n')
        data = b""
        while data.count(b"\n") < 2:
            data += self.peer.recv(4096)
        self.assertEqual([json.loads(x) for x in data.splitlines()],
                         [{"type": "hello_ack", "protocol": 1}, VIDEO_CONFIG])
        prepare.assert_not_called()
        self.peer.sendall(b'{"type":"video_config_ack"}\n')
        worker.join(1)
        prepare.assert_called_once()
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome, [42])

    def test_interrupt_before_hello_sends_no_goodbye_or_source(self):
        prepare, video, process = Mock(), Mock(), Mock()
        with patch.object(self.control, "read", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                poc.run_session(self.control, video, process, prepare_source=prepare)
        prepare.assert_not_called(); video.assert_not_called(); process.assert_not_called()
        self.assertEqual(self.peer.recv(4096), b"")
        self.assertEqual(self.control.state, "CLOSED")

    def test_video_config_stays_fixed(self):
        self.assertEqual(VIDEO_CONFIG, {"type": "video_config", "codec": "h264",
                                       "width": 1280, "height": 720, "fps": 30})

    def test_both_acks_allow_video(self):
        self.peer.sendall(b'{"type":"hello","protocol":1}\n{"type":"video_config_ack"}\n')
        start = Mock(return_value=42)
        self.assertEqual(self.control.begin_video(start), 42)
        start.assert_called_once()
        self.assertEqual(self.control.state, "STREAMING")

    def assert_no_video(self, replies, exception):
        if replies:
            self.peer.sendall(replies)
        open_video, process, prepare_source = Mock(), Mock(), Mock()
        with self.assertRaises(exception):
            poc.run_session(self.control, open_video, process, prepare_source=prepare_source)
        prepare_source.assert_not_called()
        open_video.assert_not_called()
        process.assert_not_called()
        self.assertEqual(self.control.state, "CLOSED")
        self.assertEqual(self.host.fileno(), -1)

    def test_partial_hello_timeout_cleanup(self):
        self.assert_no_video(b'{"type":', TimeoutError)

    def test_missing_config_ack_timeout_cleanup(self):
        self.assert_no_video(b'{"type":"hello","protocol":1}\n', TimeoutError)

    def test_wrong_protocol_no_video(self):
        self.assert_no_video(b'{"type":"hello","protocol":2}\n', ProtocolError)

    def test_bool_is_not_protocol_integer(self):
        self.assert_no_video(b'{"type":"hello","protocol":true}\n', ProtocolError)

    def test_invalid_json_no_video(self):
        self.assert_no_video(b'{invalid}\n', ProtocolError)

    def test_missing_type_no_video(self):
        self.assert_no_video(b'{"protocol":1}\n', ProtocolError)

    def test_unexpected_ack_no_video(self):
        self.assert_no_video(b'{"type":"video_config_ack"}\n', ProtocolError)

    def test_invalid_config_ack_no_video(self):
        self.assert_no_video(b'{"type":"hello","protocol":1}\n{"type":"goodbye"}\n', ProtocolError)

    def test_oversize_no_video(self):
        self.assert_no_video(b'x'*(MAX_LINE+1), ProtocolError)

    def test_eof_handshake_cleanup(self):
        self.peer.shutdown(socket.SHUT_WR)
        self.assert_no_video(b"", TransportClosed)

    def test_duplicate_fields(self):
        self.assert_no_video(b'{"type":"hello","type":"hello","protocol":1}\n', ProtocolError)

    def test_invalid_utf8(self):
        self.assert_no_video(b'\xff\n', ProtocolError)

    def test_control_eof_during_streaming_reaps_process(self):
        self.peer.sendall(b'{"type":"hello","protocol":1}\n{"type":"video_config_ack"}\n')
        self.peer.shutdown(socket.SHUT_WR)
        video, remote = socket.socketpair(socket.AF_UNIX)
        self.addCleanup(remote.close)
        process = Mock(returncode=0)
        process.poll.return_value = None
        process.wait.return_value = 0
        self.assertEqual(poc.run_session(self.control, lambda: video, lambda _: process), 2)
        process.send_signal.assert_called()
        process.wait.assert_called()
        self.assertEqual(video.fileno(), -1)
        self.assertEqual(self.host.fileno(), -1)

    def test_control_eof_does_not_hide_pipeline_failure(self):
        self.peer.sendall(b'{"type":"hello","protocol":1}\n{"type":"video_config_ack"}\n')
        self.peer.shutdown(socket.SHUT_WR)
        video, remote = socket.socketpair(socket.AF_UNIX)
        self.addCleanup(remote.close)
        process = Mock(returncode=9)
        process.poll.return_value = None
        process.wait.return_value = 9
        with self.assertRaisesRegex(RuntimeError, "failure.*alongside control EOF"):
            poc.run_session(self.control, lambda: video, lambda _: process)
        self.assertEqual(video.fileno(), -1)
        self.assertEqual(self.host.fileno(), -1)

    def test_pipeline_failure_is_not_completion_and_cleans_up(self):
        self.peer.sendall(b'{"type":"hello","protocol":1}\n{"type":"video_config_ack"}\n')
        video, remote = socket.socketpair(socket.AF_UNIX)
        self.addCleanup(remote.close)
        process = Mock(returncode=9)
        process.poll.return_value = 9
        process.wait.return_value = 9
        with self.assertRaisesRegex(RuntimeError, "unexpected GStreamer failure"):
            poc.run_session(self.control, lambda: video, lambda _: process)
        self.assertEqual(video.fileno(), -1)
        self.assertEqual(self.host.fileno(), -1)

    def test_revoked_session_exit_is_expected_and_cleanup_is_idempotent(self):
        self.peer.sendall(b'{"type":"hello","protocol":1}\n{"type":"video_config_ack"}\n')
        video, remote = socket.socketpair(socket.AF_UNIX)
        self.addCleanup(remote.close)
        revoked = threading.Event()
        revoked.set()
        process = Mock(returncode=1)
        process.poll.return_value = 1
        process.wait.return_value = 1

        self.assertEqual(
            poc.run_session(self.control, lambda: video, lambda _: process, revoked),
            2,
        )
        self.assertEqual(video.fileno(), -1)
        self.assertEqual(self.host.fileno(), -1)
        self.control.close()

    def test_revocation_after_stream_start_uses_same_goodbye_reason(self):
        self.peer.sendall(b'{"type":"hello","protocol":1}\n{"type":"video_config_ack"}\n')
        video, remote = socket.socketpair(socket.AF_UNIX)
        self.addCleanup(remote.close)
        revoked = threading.Event()
        process = Mock(returncode=1)
        process.poll.return_value = None

        def start_pipeline(_stream):
            revoked.set()
            return process

        self.assertEqual(
            poc.run_session(self.control, lambda: video, start_pipeline, revoked),
            2,
        )
        self.assertTrue(
            self.peer.recv(4096).endswith(
                b'{"type":"goodbye","reason":"transport_closed"}\n'
            )
        )
        process.send_signal.assert_called()
        self.assertEqual(video.fileno(), -1)
        self.assertEqual(self.host.fileno(), -1)

    def test_fragmented_line_and_goodbye(self):
        for byte in b'{"type":"goodbye","reason":"completed"}\n':
            self.peer.sendall(bytes([byte]))
        self.assertEqual(self.control.read(), {"type":"goodbye","reason":"completed"})
        self.control.goodbye("completed")
        self.assertEqual(self.control.state, "CLOSING")
        self.assertIn(b'"goodbye"',self.peer.recv(4096))


if __name__ == "__main__":
    unittest.main()
