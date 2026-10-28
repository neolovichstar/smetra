"""Keep disposable UI fixtures on loopback, even if a provider mock is missing."""
import ipaddress
import os
import sys


def restrict_to_loopback():
    # A loopback HTTP proxy could forward a blocked external hostname. Fixtures
    # need direct local sockets only, so remove inherited outbound proxy routes.
    for name in tuple(os.environ):
        if name.lower() in ("http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(name, None)
    def guard(event, args):
        if event == "socket.getaddrinfo":
            host = args[0]
        elif event == "socket.connect" and isinstance(args[1], tuple):
            host = args[1][0]
        else:
            return
        if host == "localhost":
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except ValueError:
            pass
        raise OSError("Isolated UI fixtures allow only loopback connections")

    sys.addaudithook(guard)
