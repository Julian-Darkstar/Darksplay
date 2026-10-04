"""Unit tests for tools/screencast_portal.py and PipeWire pipeline construction."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from screencast_portal import (
    PortalCancelled,
    PortalError,
    PortalScreenCast,
)
import importlib.util
spec = importlib.util.spec_from_file_location("video_poc", Path(__file__).parents[1] / "tools/video-poc.py")
poc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)


class PipelineConstructionChecks(unittest.TestCase):
    def test_pipewire_pipeline_arguments(self):
        pipeline = poc.pipewire_pipeline_args(
            video_fd=10,
            pw_fd=5,
            node_id=42,
            seconds=5,
            keepalive_ms=1000,
        )
        self.assertIn("pipewiresrc", pipeline)
        self.assertIn("fd=5", pipeline)
        self.assertIn("path=42", pipeline)
        self.assertIn("do-timestamp=true", pipeline)
        self.assertIn("keepalive-time=1000", pipeline)
        self.assertIn("num-buffers=150", pipeline)  # 5s * 30fps

        # Framerate stabilization
        self.assertIn("videorate", pipeline)
        self.assertIn("video/x-raw,framerate=30/1", pipeline)

        # Aspect ratio preservation & scaling
        self.assertIn("videoscale", pipeline)
        self.assertIn("add-borders=true", pipeline)
        self.assertIn("video/x-raw,width=1280,height=720,pixel-aspect-ratio=1/1", pipeline)

        # Color conversion & encoding
        self.assertIn("video/x-raw,format=I420", pipeline)
        self.assertIn("openh264enc", pipeline)
        self.assertIn("bitrate=4000000", pipeline)
        self.assertIn("rate-control=bitrate", pipeline)
        self.assertIn("gop-size=30", pipeline)
        self.assertIn("complexity=low", pipeline)
        self.assertIn("enable-frame-skip=false", pipeline)

        # Annex B parsing & sink
        self.assertIn("h264parse", pipeline)
        self.assertIn("config-interval=-1", pipeline)
        self.assertIn("video/x-h264,stream-format=byte-stream,alignment=au,profile=constrained-baseline", pipeline)
        self.assertIn("fdsink", pipeline)
        self.assertIn("fd=10", pipeline)
        self.assertIn("sync=false", pipeline)

    def test_pipewire_pipeline_infinite_duration(self):
        pipeline = poc.pipewire_pipeline_args(
            video_fd=11,
            pw_fd=6,
            node_id=99,
            seconds=0,
            keepalive_ms=500,
        )
        self.assertNotIn("num-buffers=0", pipeline)
        self.assertFalse(any(arg.startswith("num-buffers=") for arg in pipeline))
        self.assertIn("keepalive-time=500", pipeline)

    def test_synthetic_pipeline_preserved(self):
        pipeline = poc.pipeline_args_synthetic(7, seconds=2)
        self.assertIn("videotestsrc", pipeline)
        self.assertIn("num-buffers=60", pipeline)
        self.assertIn("fd=7", pipeline)
        self.assertEqual(poc.pipeline_args, poc.pipeline_args_synthetic)


class PortalProtocolChecks(unittest.TestCase):
    def setUp(self):
        self.mock_bus = MagicMock()
        self.mock_bus.get_unique_name.return_value = ":1.42"
        self.mock_portal_obj = MagicMock()
        self.mock_screencast = MagicMock()
        self.mock_bus.get_object.return_value = self.mock_portal_obj

    @patch("dbus.SessionBus")
    @patch("dbus.Interface")
    def test_create_session_success(self, mock_iface, mock_sbus):
        mock_sbus.return_value = self.mock_bus
        mock_iface.return_value = self.mock_screencast

        portal = PortalScreenCast()
        portal._call_request = MagicMock(return_value=(0, {"session_handle": "/test/handle"}))

        handle = portal._create_session()
        self.assertEqual(handle, "/test/handle")

    @patch("dbus.SessionBus")
    @patch("dbus.Interface")
    def test_create_session_cancelled(self, mock_iface, mock_sbus):
        mock_sbus.return_value = self.mock_bus
        mock_iface.return_value = self.mock_screencast

        portal = PortalScreenCast()
        portal._call_request = MagicMock(return_value=(1, {}))

        with self.assertRaises(PortalCancelled):
            portal._create_session()

    @patch("dbus.SessionBus")
    @patch("dbus.Interface")
    def test_select_sources_options(self, mock_iface, mock_sbus):
        mock_sbus.return_value = self.mock_bus
        mock_iface.return_value = self.mock_screencast

        portal = PortalScreenCast()
        captured_opts = {}

        def mock_call(caller, opts):
            captured_opts.update(opts)
            return (0, {})

        portal._call_request = mock_call
        portal._select_sources("/test/session")

        self.assertEqual(int(captured_opts["types"]), 1)  # MONITOR
        self.assertEqual(captured_opts["multiple"], False)
        self.assertEqual(int(captured_opts["cursor_mode"]), 2)  # EMBEDDED
        self.assertEqual(int(captured_opts["persist_mode"]), 0)  # DO NOT PERSIST

    @patch("dbus.SessionBus")
    @patch("dbus.Interface")
    def test_start_extracts_stream_metadata(self, mock_iface, mock_sbus):
        mock_sbus.return_value = self.mock_bus
        mock_iface.return_value = self.mock_screencast

        portal = PortalScreenCast()
        streams_result = [
            (97, {"id": "0", "source_type": 1, "size": (1920, 1080)})
        ]
        portal._call_request = MagicMock(return_value=(0, {"streams": streams_result}))

        streams = portal._start("/test/session")
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0][0], 97)
        self.assertEqual(streams[0][1]["size"], (1920, 1080))

    @patch("dbus.SessionBus")
    @patch("dbus.Interface")
    def test_start_user_cancelled_in_gnome_dialog(self, mock_iface, mock_sbus):
        mock_sbus.return_value = self.mock_bus
        mock_iface.return_value = self.mock_screencast

        portal = PortalScreenCast()
        portal._call_request = MagicMock(return_value=(1, {}))

        with self.assertRaises(PortalCancelled):
            portal._start("/test/session")

    @patch("dbus.SessionBus")
    @patch("dbus.Interface")
    def test_start_empty_streams_raises_error(self, mock_iface, mock_sbus):
        mock_sbus.return_value = self.mock_bus
        mock_iface.return_value = self.mock_screencast

        portal = PortalScreenCast()
        portal._create_session = MagicMock(return_value="/test/session")
        portal._select_sources = MagicMock()
        portal._start = MagicMock(return_value=[])  # Empty streams

        with self.assertRaisesRegex(PortalError, "returned no streams"):
            portal.open()

    @patch("dbus.SessionBus")
    @patch("dbus.Interface")
    def test_close_idempotent(self, mock_iface, mock_sbus):
        mock_sbus.return_value = self.mock_bus
        mock_iface.return_value = self.mock_screencast

        portal = PortalScreenCast()
        portal.session_handle = "/test/session"
        portal.pipewire_fd = None

        mock_session_obj = MagicMock()
        self.mock_bus.get_object.return_value = mock_session_obj

        portal.close()
        mock_session_obj.Close.assert_called_once()
        self.assertIsNone(portal.session_handle)

        # Calling close again should do nothing and not raise
        portal.close()
        self.assertEqual(mock_session_obj.Close.call_count, 1)

    @patch("dbus.SessionBus")
    @patch("dbus.Interface")
    def test_session_closed_marks_revocation_and_calls_callback_once(self, mock_iface, mock_sbus):
        mock_sbus.return_value = self.mock_bus
        mock_iface.return_value = self.mock_screencast
        callback = MagicMock()
        portal = PortalScreenCast(on_closed=callback)

        # dbus-python invokes signal handlers with the signal payload in addition to self.
        portal._handle_session_closed("session-closed-payload")
        portal._handle_session_closed("duplicate-payload")

        self.assertTrue(portal.externally_closed)
        self.assertEqual(callback.call_count, 1)


if __name__ == "__main__":
    unittest.main()
