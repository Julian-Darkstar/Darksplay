#!/usr/bin/env python3
"""Opt-in physical USB checks. Requires Darksplay open; never launches GStreamer."""
import argparse
import json
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    args = parser.parse_args()
    adb = ['adb', '-s', args.serial]
    devices = subprocess.check_output(['adb', 'devices', '-l'], text=True)
    assert any(line.split()[:2] == [args.serial, 'device'] and 'usb:' in line
               for line in devices.splitlines()), 'authorized physical USB required'
    def command(*arguments):
        return subprocess.check_output(adb + list(arguments), text=True)
    def ui():
        command('shell', 'uiautomator', 'dump', '/data/local/tmp/darksplay-session-check.xml')
        return ET.fromstring(command('shell', 'cat', '/data/local/tmp/darksplay-session-check.xml'))
    def button(name):
        node = next(n for n in ui().iter('node') if n.get('resource-id', '').endswith('/' + name))
        assert node.get('enabled') == 'true', name + ' disabled'
        x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.get('bounds')))
        command('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))
        if name == 'start_receiver':
            assert any(n.get('text') == 'Waiting for host' for n in ui().iter('node')), 'receiver not ready'
    def stopped():
        nodes = list(ui().iter('node'))
        assert next(n for n in nodes if n.get('resource-id', '').endswith('/start_receiver')).get('enabled') == 'true'
        assert next(n for n in nodes if n.get('resource-id', '').endswith('/stop_receiver')).get('enabled') == 'false'
        return next(n.get('text') for n in nodes if n.get('resource-id', '').endswith('/status'))
    root = Path(__file__).resolve().parent.parent / 'build' / 'session-poc'
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='check-', dir=root) as temporary:
        local = 'localfilesystem:' + str(Path(temporary) / 'control.sock')
        command('forward', '--no-rebind', local, 'localabstract:io.darkstar.darksplay.control')
        try:
            button('start_receiver')
            button('stop_receiver')
            print('B stop waiting:', stopped(), flush=True)
            cases = [
                ('wrong protocol', b'{"type":"hello","protocol":2}\n', False),
                ('invalid JSON', b'{bad}\n', False),
                ('missing type', b'{"protocol":1}\n', False),
                ('config before hello', b'{"type":"video_config"}\n', False),
                ('unexpected message', b'{"type":"ping"}\n', False),
                ('oversize', b'x' * 4097, False),
                ('duplicate key', b'{"type":"hello","protocol":1,"protocol":1}\n', False),
                ('invalid UTF8', b'\xff\n', False),
                ('partial EOF', b'{"type":', False),
                ('handshake timeout', None, False),
                ('unsupported codec', {'codec':'hevc'}, True),
                ('invalid width', {'width':0}, True),
                ('invalid height', {'height':0}, True),
                ('invalid fps', {'fps':0}, True),
                ('C stop during handshake', 'stop', True),
            ]
            for name, payload, hello_first in cases:
                button('start_receiver')
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                    stream.settimeout(8)
                    stream.connect(local.removeprefix('localfilesystem:'))
                    if hello_first:
                        stream.sendall(b'{"type":"hello","protocol":1}\n')
                        ack = stream.recv(4096)
                        assert json.loads(ack) == {'type':'hello_ack','protocol':1}, ack
                    if payload == 'stop':
                        button('stop_receiver')
                    elif isinstance(payload, dict):
                        config = dict(type='video_config', codec='h264', width=1280, height=720, fps=30)
                        config.update(payload)
                        stream.sendall((json.dumps(config)+'\n').encode())
                    elif payload is not None:
                        stream.sendall(payload)
                        if name == 'partial EOF':
                            stream.shutdown(socket.SHUT_WR)
                    try:
                        received = stream.recv(4096)
                    except ConnectionResetError:
                        received = b''
                    assert received == b'', (name, received)
                # UI query supplies enough time for finally without a fixed sleep.
                print(name + ': closed; ' + stopped(), flush=True)
        finally:
            command('forward', '--remove', local)
    print('Physical control rejection/cleanup checks passed; no video process created', flush=True)


if __name__ == '__main__':
    main()
