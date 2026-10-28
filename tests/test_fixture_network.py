"""A missing UI fixture mock cannot send data or even resolve an external host."""
import subprocess
import sys
import unittest


class FixtureNetworkTests(unittest.TestCase):
    def test_external_dns_and_connections_are_blocked_but_loopback_works(self):
        result = subprocess.run([sys.executable, "-c", """
import socket
from scripts.fixture_network import restrict_to_loopback
restrict_to_loopback()
for operation in (
    lambda: socket.getaddrinfo('openrouter.ai', 443),
    lambda: socket.socket().connect(('198.51.100.1', 443)),
):
    try:
        operation()
    except OSError as error:
        assert str(error) == 'Isolated UI fixtures allow only loopback connections'
    else:
        raise AssertionError('External networking was allowed')
listener = socket.socket()
listener.bind(('127.0.0.1', 0))
listener.listen(1)
client = socket.create_connection(listener.getsockname())
peer, _ = listener.accept()
client.sendall(b'local fixture')
assert peer.recv(100) == b'local fixture'
peer.close()
client.close()
listener.close()
"""], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
