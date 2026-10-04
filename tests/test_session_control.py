"""Actual sender and NDJSON transport over AF_UNIX, no Android or new packages."""
import importlib.util
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from session_control import Control, ProtocolError, TransportClosed, MAX_LINE
spec = importlib.util.spec_from_file_location("video_poc", Path(__file__).parents[1] / "tools/video-poc.py")
poc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)


class ControlChecks(unittest.TestCase):
    def setUp(self):
        self.host, self.peer = socket.socketpair(socket.AF_UNIX)
        self.addCleanup(self.host.close)
        self.addCleanup(self.peer.close)
        self.control = Control(self.host, timeout=0.03)

    def test_both_acks_allow_video(self):
        self.peer.sendall(b'{"type":"hello_ack","protocol":1}\n{"type":"video_config_ack"}\n')
        start = Mock(return_value=42)
        self.assertEqual(self.control.begin_video(start), 42)
        start.assert_called_once()
        self.assertEqual(self.control.state, "STREAMING")

    def assert_no_video(self, replies, exception):
        if replies:
            self.peer.sendall(replies)
        open_video, process = Mock(), Mock()
        with self.assertRaises(exception):
            poc.run_session(self.control, open_video, process)
        open_video.assert_not_called()
        process.assert_not_called()
        self.assertEqual(self.control.state, "CLOSED")
        self.assertEqual(self.host.fileno(), -1)

    def test_missing_hello_ack_timeout_cleanup(self):
        self.assert_no_video(b"", TimeoutError)

    def test_missing_config_ack_timeout_cleanup(self):
        self.assert_no_video(b'{"type":"hello_ack","protocol":1}\n', TimeoutError)

    def test_wrong_protocol_no_video(self):
        self.assert_no_video(b'{"type":"hello_ack","protocol":2}\n', ProtocolError)

    def test_bool_is_not_protocol_integer(self):
        self.assert_no_video(b'{"type":"hello_ack","protocol":true}\n', ProtocolError)

    def test_invalid_json_no_video(self):
        self.assert_no_video(b'{invalid}\n', ProtocolError)

    def test_missing_type_no_video(self):
        self.assert_no_video(b'{"protocol":1}\n', ProtocolError)

    def test_unexpected_ack_no_video(self):
        self.assert_no_video(b'{"type":"video_config_ack"}\n', ProtocolError)

    def test_invalid_config_ack_no_video(self):
        self.assert_no_video(b'{"type":"hello_ack","protocol":1}\n{"type":"goodbye"}\n', ProtocolError)

    def test_oversize_no_video(self):
        self.assert_no_video(b'x'*(MAX_LINE+1), ProtocolError)

    def test_eof_handshake_cleanup(self):
        self.peer.shutdown(socket.SHUT_WR)
        self.assert_no_video(b"", TransportClosed)

    def test_duplicate_fields(self):
        self.assert_no_video(b'{"type":"hello_ack","type":"hello_ack","protocol":1}\n', ProtocolError)

    def test_invalid_utf8(self):
        self.assert_no_video(b'\xff\n', ProtocolError)

    def test_control_eof_during_streaming_reaps_process(self):
        self.peer.sendall(b'{"type":"hello_ack","protocol":1}\n{"type":"video_config_ack"}\n')
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
        self.peer.sendall(b'{"type":"hello_ack","protocol":1}\n{"type":"video_config_ack"}\n')
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
        self.peer.sendall(b'{"type":"hello_ack","protocol":1}\n{"type":"video_config_ack"}\n')
        video, remote = socket.socketpair(socket.AF_UNIX)
        self.addCleanup(remote.close)
        process = Mock(returncode=9)
        process.poll.return_value = 9
        process.wait.return_value = 9
        with self.assertRaisesRegex(RuntimeError, "unexpected GStreamer failure"):
            poc.run_session(self.control, lambda: video, lambda _: process)
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
