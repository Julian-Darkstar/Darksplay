"""Sender exit classification on real AF_UNIX pairs; no device or dependencies."""
import importlib.util
from pathlib import Path
import signal
import socket
import threading
import unittest
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

spec = importlib.util.spec_from_file_location("video_poc", Path(__file__).parents[1] / "tools/video-poc.py")
poc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)


class ExitClassification(unittest.TestCase):
    def setUp(self):
        self.sender, self.receiver = socket.socketpair(socket.AF_UNIX)
        self.addCleanup(self.sender.close)
        self.addCleanup(self.receiver.close)

    def test_completion(self):
        self.assertEqual(poc.classify_pipeline_exit(0, self.sender), 0)

    def test_sigpipe_with_confirmed_peer_eof_is_interruption_not_success(self):
        self.receiver.close()
        self.assertEqual(poc.classify_pipeline_exit(-signal.SIGPIPE, self.sender), 2)

    def test_sigpipe_with_live_peer_is_failure(self):
        with self.assertRaisesRegex(RuntimeError, "exit=-13"):
            poc.classify_pipeline_exit(-signal.SIGPIPE, self.sender)

    def test_sigpipe_with_incoming_data_does_not_confirm_eof(self):
        self.receiver.sendall(b"unexpected")
        with self.assertRaisesRegex(RuntimeError, "unexpected GStreamer"):
            poc.classify_pipeline_exit(-signal.SIGPIPE, self.sender)
        self.assertEqual(self.sender.recv(10), b"unexpected")  # peek is non-destructive

    def test_other_error_is_failure_even_with_closed_peer(self):
        self.receiver.close()
        with self.assertRaisesRegex(RuntimeError, "exit=1"):
            poc.classify_pipeline_exit(1, self.sender)

    def test_revoked_session_makes_gstreamer_exit_expected(self):
        revoked = threading.Event()
        revoked.set()
        self.assertEqual(poc.classify_pipeline_exit(1, self.sender, revoked.is_set()), 2)

    def test_unrelated_signal_is_failure(self):
        self.receiver.close()
        with self.assertRaisesRegex(RuntimeError, "unexpected GStreamer"):
            poc.classify_pipeline_exit(-signal.SIGTERM, self.sender)


if __name__ == "__main__":
    unittest.main()
