# SPDX-License-Identifier: GPL-3.0-or-later
"""Rentalars Gateway link: the server's side of the protocol RGW1.

The gateway (a separate program in the DMZ) lets apps reach this installation from the internet without a
port being opened in the internal network: this installation calls the gateway, never the other way round.
Everything the apps send travels end to end encrypted; this package opens it, carries it out against the
application itself (``/api/v1/`` only) and seals the answer.

Nothing here changes how the application works: the apps' direct way to the server stays as it is, and an
installation that never runs ``rentalars gateway connect`` is not touched (no service, no connection).

``protocol``   the formats (a copy of ``rentalars_gateway/protocol.py``, checked against the test vectors)
``models``     paired devices, open pairing offers, seen request ids, the link to the gateway, token bindings
``service``    the polling service and the processing of one request
``binding``    tokens issued through the gateway work only through the device they were issued for
``management/commands/gateway.py``  the command ``rentalars gateway …``
"""
