"""Darksplay V0.2 — xdg-desktop-portal ScreenCast client.

Interacts with org.freedesktop.portal.ScreenCast over D-Bus to obtain a
PipeWire file descriptor and stream node ID for an existing display monitor or a virtual display.

Lifecycle & Ownership:
  - Owns the D-Bus session and signal subscriptions for portal requests.
  - Owns the portal session handle on D-Bus; calls Session.Close() on teardown.
  - Owns the PipeWire Unix file descriptor; closes it on teardown.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

log = logging.getLogger("darksplay.portal")

PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"


MONITOR = 1
VIRTUAL = 4


class PortalError(RuntimeError):
    """Generic portal interaction error."""
    pass


class PortalCancelled(Exception):
    """User explicitly cancelled the portal screen selection dialog."""
    pass


class PortalScreenCast:
    """Manages the lifecycle of an xdg-desktop-portal ScreenCast session.

    Usage:
        with PortalScreenCast() as portal:
            pw_fd = portal.pipewire_fd
            node_id = portal.node_id
            ...
    """

    def __init__(self, on_closed: Optional[Callable[[], None]] = None, *, source_type: int = MONITOR) -> None:
        if source_type not in (MONITOR, VIRTUAL):
            raise ValueError("source_type must be MONITOR or VIRTUAL")
        self.source_type = source_type
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self._bus = dbus.SessionBus()
        self._portal_obj = self._bus.get_object(PORTAL_BUS_NAME, PORTAL_OBJECT_PATH)
        self._screencast = dbus.Interface(self._portal_obj, SCREENCAST_IFACE)

        sender = self._bus.get_unique_name().lstrip(":").replace(".", "_")
        self._sender_prefix = sender

        self.session_handle: Optional[str] = None
        self.pipewire_fd: Optional[int] = None
        self.node_id: Optional[int] = None
        self.stream_properties: Dict[str, Any] = {}
        self._session_closed_match = None
        self._on_closed = on_closed
        self._closed = False
        self._externally_closed = threading.Event()
        self._dispatch_loop = None
        self._dispatch_thread = None

    def open(self) -> PortalScreenCast:
        """Execute the full portal sequence: CreateSession -> SelectSources -> Start -> OpenPipeWireRemote."""
        try:
            # 1. CreateSession
            self.session_handle = self._create_session()
            log.info("Portal session created: %s", self.session_handle)

            # Subscribe to external session closure (e.g. user stops sharing from GNOME top bar)
            self._session_closed_match = self._bus.add_signal_receiver(
                self._handle_session_closed,
                signal_name="Closed",
                dbus_interface=SESSION_IFACE,
                path=self.session_handle,
            )

            # 2. SelectSources (monitor, single, embedded cursor, no persist)
            self._select_sources(self.session_handle)
            log.info("Portal SelectSources completed (source_type=%d, embedded cursor)", self.source_type)

            # 3. Start (pops up GNOME dialog for user consent)
            log.info("Awaiting user screen selection in GNOME dialog...")
            streams = self._start(self.session_handle)
            if not streams:
                raise PortalError("ScreenCast Start returned no streams")

            if self.source_type == VIRTUAL and (len(streams) != 1 or
                    int(streams[0][1].get("source_type", -1)) != VIRTUAL):
                raise PortalError("Expected exactly one VIRTUAL stream")

            # Extract first stream (node_id and properties)
            first_stream = streams[0]
            self.node_id = int(first_stream[0])
            self.stream_properties = dict(first_stream[1]) if len(first_stream) > 1 else {}
            log.info("ScreenCast stream obtained: node_id=%d, props=%s", self.node_id, self.stream_properties)

            # 4. OpenPipeWireRemote
            raw_fd = self._open_pipewire_remote(self.session_handle)
            self.pipewire_fd = os.dup(raw_fd)
            # Close the temporary fd from dbus-python if take() was not used
            try:
                os.close(raw_fd)
            except OSError:
                pass
            log.info("PipeWire remote FD obtained: %d", self.pipewire_fd)

            return self

        except BaseException:
            self.close()
            raise

    def _call_request(
        self,
        method_caller: Callable[[str, Dict[str, Any]], Any],
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """Helper to invoke a portal method with handle_token and await its Response signal synchronously."""
        token = f"darksplay_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        expected_path = f"/org/freedesktop/portal/desktop/request/{self._sender_prefix}/{token}"

        loop = GLib.MainLoop()
        result_box: Dict[str, Tuple[int, Dict[str, Any]]] = {}

        def on_response(response: int, results: Dict[str, Any]) -> None:
            result_box["response"] = (int(response), dict(results))
            loop.quit()

        match = self._bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface=REQUEST_IFACE,
            path=expected_path,
        )

        options: Dict[str, Any] = {"handle_token": token}
        if extra_options:
            options.update(extra_options)

        try:
            req_path = method_caller(options)
            if str(req_path) != expected_path:
                log.warning("Portal returned request path %s != expected %s", req_path, expected_path)
            loop.run()
        finally:
            match.remove()

        if "response" not in result_box:
            raise PortalError("Portal request did not receive a response")

        return result_box["response"]

    def _create_session(self) -> str:
        session_token = f"sess_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        opts = {
            "session_handle_token": session_token,
        }
        code, results = self._call_request(
            lambda o: self._screencast.CreateSession(o),
            opts,
        )
        if code != 0:
            if code == 1:
                raise PortalCancelled("CreateSession cancelled by user")
            raise PortalError(f"CreateSession failed with code {code}")
        return str(results["session_handle"])

    def _select_sources(self, session_handle: str) -> None:
        opts: Dict[str, Any] = {
            "types": dbus.UInt32(self.source_type), # MONITOR or VIRTUAL
            "multiple": False,             # single source
            "cursor_mode": dbus.UInt32(2), # 2 = EMBEDDED
            "persist_mode": dbus.UInt32(0),# 0 = DO NOT PERSIST
        }
        code, _ = self._call_request(
            lambda o: self._screencast.SelectSources(session_handle, o),
            opts,
        )
        if code != 0:
            if code == 1:
                raise PortalCancelled("SelectSources cancelled by user")
            raise PortalError(f"SelectSources failed with code {code}")

    def _start(self, session_handle: str) -> list:
        code, results = self._call_request(
            lambda o: self._screencast.Start(session_handle, "", o),
            {},
        )
        if code != 0:
            if code == 1:
                raise PortalCancelled("Screen selection cancelled by user in GNOME dialog")
            raise PortalError(f"Start failed with code {code}")
        return list(results.get("streams", []))

    def _open_pipewire_remote(self, session_handle: str) -> int:
        fd_obj = self._screencast.OpenPipeWireRemote(session_handle, {})
        if hasattr(fd_obj, "take"):
            return fd_obj.take()
        return int(fd_obj)

    def _handle_session_closed(self, *signal_args: Any) -> None:
        log.warning("ScreenCast session was closed externally by portal / GNOME")
        if self._externally_closed.is_set():
            return
        self._externally_closed.set()
        if self._on_closed and not self._closed:
            self._on_closed()

    @property
    def externally_closed(self) -> bool:
        return self._externally_closed.is_set()

    def start_dispatch(self) -> None:
        """Run the GLib context needed to receive portal signals while streaming."""
        if self._dispatch_thread is not None:
            return
        self._dispatch_loop = GLib.MainLoop()
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop.run,
            name="darksplay-portal-dispatch",
            daemon=True,
        )
        self._dispatch_thread.start()

    def stop_dispatch(self) -> None:
        """Stop signal dispatch; safe to call more than once."""
        if self._dispatch_loop is None:
            return
        self._dispatch_loop.quit()
        if self._dispatch_thread is not threading.current_thread():
            self._dispatch_thread.join(timeout=1)
        self._dispatch_loop = None
        self._dispatch_thread = None

    def close(self) -> None:
        """Idempotent teardown of portal session, file descriptor, and signal handlers."""
        if self._closed:
            return
        self._closed = True
        self.stop_dispatch()

        if self._session_closed_match is not None:
            try:
                self._session_closed_match.remove()
            except Exception:
                pass
            self._session_closed_match = None

        if self.pipewire_fd is not None:
            try:
                os.close(self.pipewire_fd)
                log.info("Closed PipeWire FD %d", self.pipewire_fd)
            except OSError:
                pass
            self.pipewire_fd = None

        if self.session_handle is not None:
            try:
                sess_obj = self._bus.get_object(PORTAL_BUS_NAME, self.session_handle)
                sess_obj.Close(dbus_interface=SESSION_IFACE)
                log.info("Closed portal session %s", self.session_handle)
            except Exception as e:
                log.debug("Session.Close() exception (may already be closed): %s", e)
            self.session_handle = None

    def __enter__(self) -> PortalScreenCast:
        return self.open()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
