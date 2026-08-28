"""The adapter for the Arduino the lab runs today.

Everything hardware specific lives in this package: the query string format,
the zero padding, the trailing logout parameter, the request window, the
answer that is always HTTP 200, and the slot range. Nothing above the adapter
sees a URL.
"""

from .controller import OacEthernetConfig, OacEthernetController
from .transport import SocketTransport, Transport

__all__ = ["OacEthernetConfig", "OacEthernetController", "SocketTransport",
           "Transport"]
