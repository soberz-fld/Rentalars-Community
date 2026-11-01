# SPDX-License-Identifier: GPL-3.0-or-later
"""The Rentalars Gateway protocol, version 1.

This file is a copy of ``rentalars_gateway/protocol.py`` of the Rentalars Gateway repository (docs/protokoll.md
there is the specification). It is kept identical on purpose; ``tests/unit/test_111_gateway_link.py`` computes
the test vectors of the gateway (``docs/testvektoren.json``) with it. Change it only together with the gateway.

The original says: this module is shared by the gateway and by its two kinds of clients. The gateway itself only *verifies*
signatures and reads a few header fields; it never opens a sealed message. The server and the apps seal and
open. The server team can take this file as it is (it is the reference implementation of the formats); the
apps re-implement it with the primitives of their platform and check themselves against
``docs/testvektoren.json``.

Primitives (all of them exist on Android 6+ and in iOS CryptoKit without any extra library):

* ECDH and ECDSA on NIST P-256 (secp256r1); public keys travel as the 65 bytes of the uncompressed point,
  signatures as ASN.1 DER.
* HKDF-SHA256 (RFC 5869), AES-256-GCM with a 12 byte nonce, SHA-256.

Nothing here talks to the network or to the file system.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import struct
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PROTOCOL_VERSION = 1

CURVE = ec.SECP256R1()
POINT_LEN = 65  # 0x04 || X || Y
ID_LEN = 16  # device id, request id, pairing id
SECRET_LEN = 32  # pairing secret
NONCE_LEN = 12
TAG_LEN = 16
PAD_BLOCK = 1024  # plaintext is padded to a multiple of this before it is sealed
ZERO_SALT = bytes(32)

CALL = "call"
PAIR = "pair"
_CONTEXTS = (CALL, PAIR)

_B64URL = re.compile(r"^[A-Za-z0-9_-]*$")


class ProtocolError(Exception):
    """A message is malformed, not authentic or not acceptable. The text is for logs, never for a peer."""


# --- Encoding --------------------------------------------------------------------------------------------------


def b64e(data: bytes) -> str:
    """Base64url without padding, the encoding of every binary value in a header, a QR code or a JSON file."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64d(text: str, *, length: int | None = None, max_length: int = 1 << 20) -> bytes:
    """Decode base64url (no padding, no other characters); optionally demand an exact length."""
    if not isinstance(text, str) or len(text) > max_length * 2 or not _B64URL.fullmatch(text) or len(text) % 4 == 1:
        raise ProtocolError("bad base64url")
    try:
        data = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except ValueError as error:  # binascii.Error
        raise ProtocolError("bad base64url") from error
    if length is not None and len(data) != length:
        raise ProtocolError("bad length")
    return data


def u64(value: int) -> bytes:
    """An unsigned 64 bit number, big endian; raises :class:`ProtocolError` for a number that does not fit."""
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < 1 << 64:
        raise ProtocolError("number out of range")
    return struct.pack(">Q", value)


def is_version(value: object) -> bool:
    """True if ``value`` is the protocol version as a real number (``true`` and ``1.0`` are not)."""
    return type(value) is int and value == PROTOCOL_VERSION


def sha256(data: bytes) -> bytes:
    """SHA-256."""
    return hashlib.sha256(data).digest()


# --- Keys ------------------------------------------------------------------------------------------------------


def generate_private_key() -> ec.EllipticCurvePrivateKey:
    """A new P-256 key pair (device key, server keys, one-off keys)."""
    return ec.generate_private_key(CURVE)


def public_bytes(key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey) -> bytes:
    """The 65 bytes of the uncompressed public point."""
    public = key.public_key() if isinstance(key, ec.EllipticCurvePrivateKey) else key
    return public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def load_public(point: bytes) -> ec.EllipticCurvePublicKey:
    """The public key of 65 bytes; refuses a point that is not on the curve."""
    if len(point) != POINT_LEN or point[0] != 4:
        raise ProtocolError("bad public key")
    try:
        return ec.EllipticCurvePublicKey.from_encoded_point(CURVE, point)
    except ValueError as error:
        raise ProtocolError("public key not on the curve") from error


def private_to_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    """A private key as PKCS#8 PEM, for the files of the server (mode 0600)."""
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def private_from_pem(pem: bytes) -> ec.EllipticCurvePrivateKey:
    """Read a private key written by :func:`private_to_pem`."""
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ProtocolError("not a P-256 key")
    return key


def private_from_scalar(scalar: bytes) -> ec.EllipticCurvePrivateKey:
    """A private key from its 32 byte scalar (used for the test vectors)."""
    return ec.derive_private_key(int.from_bytes(scalar, "big"), CURVE)


def device_id_of(device_public: bytes) -> bytes:
    """The id of a device: the first 16 bytes of SHA-256 of its public key. Nobody assigns it, nobody can choose it."""
    return sha256(device_public)[:ID_LEN]


def server_key_id(server_public: bytes) -> str:
    """A short, readable fingerprint of the server's key (first 8 bytes in hex groups) for screens and logs."""
    digest = sha256(server_public)[:8].hex().upper()
    return "-".join(digest[i : i + 4] for i in range(0, len(digest), 4))


# --- Signatures ------------------------------------------------------------------------------------------------


def sign(private: ec.EllipticCurvePrivateKey, data: bytes, *, deterministic: bool = False) -> bytes:
    """ECDSA over SHA-256, ASN.1 DER. ``deterministic`` (RFC 6979) is for the test vectors only."""
    if deterministic:
        return private.sign(data, ec.ECDSA(hashes.SHA256(), deterministic_signing=True))
    return private.sign(data, ec.ECDSA(hashes.SHA256()))


def verify(public: bytes | ec.EllipticCurvePublicKey, signature: bytes, data: bytes) -> bool:
    """True if ``signature`` is a valid ECDSA/SHA-256 signature of ``data`` by ``public``."""
    try:
        key = load_public(public) if isinstance(public, bytes) else public
        key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ProtocolError, ValueError):
        return False
    return True


def call_signature_input(device_id: bytes, request_id: bytes, ts: int, body: bytes) -> bytes:
    """What the device signs for ``POST /v1/call``: it binds the device, the request, the time and the sealed body."""
    return b"RGW1 call sig" + device_id + request_id + u64(ts) + sha256(body)


def link_signature_input(
    method: str, target: str, ts: int, nonce: bytes, body: bytes = b"", *, digest: bytes | None = None
) -> bytes:
    """What the server signs for every call to ``/v1/server/...``: method, target (path and query), time, nonce, body.

    The gateway checks the signature from the head of the request, before it reads the body: it takes the body's
    SHA-256 from the ``X-RGW-Digest`` header (``digest``) and compares it with the body once that has arrived.
    """
    return (
        b"RGW1 link sig\n"
        + method.encode("ascii")
        + b"\n"
        + target.encode("ascii")
        + b"\n"
        + str(ts).encode("ascii")
        + b"\n"
        + b64e(nonce).encode("ascii")
        + b"\n"
        + (digest if digest is not None else sha256(body))
    )


def pair_pop_input(pairing_id: bytes, request_id: bytes, ephemeral_public: bytes, device_public: bytes) -> bytes:
    """What a new device signs inside its pairing request to prove that it holds the private key."""
    return b"RGW1 pair pop" + pairing_id + request_id + ephemeral_public + device_public


# --- Frames: the plaintext inside a sealed message --------------------------------------------------------------


def pack_frame(meta: dict[str, Any], body: bytes = b"") -> bytes:
    """``uint32 length of the JSON || JSON (UTF-8) || body``. The meta data always carries ``"v": 1``."""
    document = dict(meta)
    document.setdefault("v", PROTOCOL_VERSION)
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded + body


def unpack_frame(frame: bytes) -> tuple[dict[str, Any], bytes]:
    """The reverse of :func:`pack_frame`."""
    if len(frame) < 4:
        raise ProtocolError("frame too short")
    (length,) = struct.unpack(">I", frame[:4])
    if length > len(frame) - 4:
        raise ProtocolError("frame inconsistent")
    try:
        meta = json.loads(frame[4 : 4 + length].decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise ProtocolError("frame meta data unreadable") from error
    if not isinstance(meta, dict) or not is_version(meta.get("v")):
        raise ProtocolError("frame version not supported")
    return meta, frame[4 + length :]


def pad(data: bytes) -> bytes:
    """Append 0x80 and zeros up to a multiple of :data:`PAD_BLOCK`, so that sizes tell the gateway little."""
    total = -(-(len(data) + 1) // PAD_BLOCK) * PAD_BLOCK
    return data + b"\x80" + bytes(total - len(data) - 1)


def unpad(data: bytes) -> bytes:
    """The reverse of :func:`pad`."""
    end = len(data.rstrip(b"\x00"))
    if end == 0 or data[end - 1] != 0x80:
        raise ProtocolError("padding wrong")
    return data[: end - 1]


# --- Sealing ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Sealed:
    """A sealed request and the key with which its answer will be sealed."""

    body: bytes
    response_key: bytes


@dataclass(frozen=True)
class Opened:
    """An opened request: its frame and the key with which the answer must be sealed."""

    frame: bytes
    response_key: bytes


def _derive(
    shared: bytes, salt: bytes, context: str, id_a: bytes, request_id: bytes, ephemeral: bytes, server: bytes
) -> tuple[bytes, bytes]:
    info = b"RGW1 " + context.encode("ascii") + b" key" + id_a + request_id + ephemeral + server
    material = HKDF(algorithm=hashes.SHA256(), length=64, salt=salt, info=info).derive(shared)
    return material[:32], material[32:]


def _aad(kind: bytes, context: str, id_a: bytes, request_id: bytes, tail: bytes = b"") -> bytes:
    return b"RGW1 " + context.encode("ascii") + kind + id_a + request_id + tail


def seal_request(
    *,
    server_public: bytes,
    id_a: bytes,
    request_id: bytes,
    ts: int,
    frame: bytes,
    context: str = CALL,
    salt: bytes = ZERO_SALT,
    ephemeral: ec.EllipticCurvePrivateKey | None = None,
    nonce: bytes | None = None,
) -> Sealed:
    """Seal a request to the server's public key with a fresh one-off key.

    ``id_a`` is the device id (``call``) or the pairing id (``pair``); for ``pair`` the ``salt`` is the pairing
    secret, so that only the holder of the QR code can produce a request the server accepts.
    ``ephemeral`` and ``nonce`` exist for the test vectors; production code leaves them out.
    """
    if context not in _CONTEXTS:
        raise ProtocolError("unknown context")
    one_off = ephemeral or generate_private_key()
    one_off_public = public_bytes(one_off)
    shared = one_off.exchange(ec.ECDH(), load_public(server_public))
    request_key, response_key = _derive(shared, salt, context, id_a, request_id, one_off_public, server_public)
    nonce = nonce if nonce is not None else os.urandom(NONCE_LEN)
    aad = _aad(b" req", context, id_a, request_id, u64(ts) + one_off_public)
    sealed = AESGCM(request_key).encrypt(nonce, pad(frame), aad)
    return Sealed(one_off_public + nonce + sealed, response_key)


def open_request(
    *,
    server_private: ec.EllipticCurvePrivateKey,
    id_a: bytes,
    request_id: bytes,
    ts: int,
    body: bytes,
    context: str = CALL,
    salt: bytes = ZERO_SALT,
) -> Opened:
    """Open a sealed request with the server's private key; raises :class:`ProtocolError` if it is not authentic."""
    if context not in _CONTEXTS:
        raise ProtocolError("unknown context")
    if len(body) < POINT_LEN + NONCE_LEN + TAG_LEN:
        raise ProtocolError("sealed request too short")
    one_off_public = body[:POINT_LEN]
    nonce = body[POINT_LEN : POINT_LEN + NONCE_LEN]
    sealed = body[POINT_LEN + NONCE_LEN :]
    shared = server_private.exchange(ec.ECDH(), load_public(one_off_public))
    request_key, response_key = _derive(
        shared, salt, context, id_a, request_id, one_off_public, public_bytes(server_private)
    )
    aad = _aad(b" req", context, id_a, request_id, u64(ts) + one_off_public)
    try:
        padded = AESGCM(request_key).decrypt(nonce, sealed, aad)
    except InvalidTag as error:
        raise ProtocolError("request not authentic") from error
    return Opened(unpad(padded), response_key)


def seal_response(
    *,
    response_key: bytes,
    id_a: bytes,
    request_id: bytes,
    frame: bytes,
    context: str = CALL,
    nonce: bytes | None = None,
) -> bytes:
    """Seal the answer to a request: ``nonce || ciphertext || tag``."""
    nonce = nonce if nonce is not None else os.urandom(NONCE_LEN)
    return nonce + AESGCM(response_key).encrypt(nonce, pad(frame), _aad(b" resp", context, id_a, request_id))


def open_response(*, response_key: bytes, id_a: bytes, request_id: bytes, body: bytes, context: str = CALL) -> bytes:
    """Open an answer; raises :class:`ProtocolError` if it was not made by the holder of the server's private key."""
    if len(body) < NONCE_LEN + TAG_LEN:
        raise ProtocolError("sealed response too short")
    try:
        padded = AESGCM(response_key).decrypt(
            body[:NONCE_LEN], body[NONCE_LEN:], _aad(b" resp", context, id_a, request_id)
        )
    except InvalidTag as error:
        raise ProtocolError("response not authentic") from error
    return unpad(padded)


# --- The texts that carry keys between people and machines -------------------------------------------------------


@dataclass(frozen=True)
class PairingOffer:
    """What the QR code of "pair a device" holds. Everything a new app needs; the secret ``ps`` is good once."""

    gateway: str  # https://gateway.example.de:8799
    gateway_fingerprint: str  # SHA-256 of the gateway's TLS certificate, lowercase hex without colons; "" if CA-signed
    server_url: str  # the address of the installation (Host and Origin inside the tunnel)
    server_public: bytes
    pairing_id: bytes
    secret: bytes
    expires: int
    name: str = ""

    PREFIX = "RGW1:"

    def encode(self) -> str:
        """``RGW1:`` followed by base64url of the JSON document."""
        document = {
            "v": PROTOCOL_VERSION,
            "gw": self.gateway,
            "gfp": self.gateway_fingerprint,
            "srv": self.server_url,
            "spk": b64e(self.server_public),
            "pid": b64e(self.pairing_id),
            "ps": b64e(self.secret),
            "exp": self.expires,
            "name": self.name,
        }
        return self.PREFIX + b64e(json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    @classmethod
    def decode(cls, text: str) -> PairingOffer:
        """Read a text made by :meth:`encode` (leading and trailing white space is ignored)."""
        text = "".join(text.split())
        if not text.startswith(cls.PREFIX):
            raise ProtocolError("not a pairing text")
        try:
            document = json.loads(b64d(text[len(cls.PREFIX) :], max_length=8192))
            if not isinstance(document, dict) or not is_version(document.get("v")):
                raise ProtocolError("pairing text of another version")
            offer = cls(
                gateway=str(document["gw"]),
                gateway_fingerprint=str(document.get("gfp", "")).lower(),
                server_url=str(document["srv"]),
                server_public=b64d(document["spk"], length=POINT_LEN),
                pairing_id=b64d(document["pid"], length=ID_LEN),
                secret=b64d(document["ps"], length=SECRET_LEN),
                expires=int(document["exp"]),
                name=str(document.get("name", "")),
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, RecursionError) as error:
            raise ProtocolError("pairing text unreadable") from error
        load_public(offer.server_public)
        return offer


@dataclass(frozen=True)
class LinkText:
    """What ``rentalars-gateway enroll`` prints for the administrator to hand to the Rentalars server."""

    gateway: str
    gateway_fingerprint: str
    token: str  # one-off enrollment token (base64url, 32 bytes)
    gateway_id: str

    PREFIX = "RGWL1:"

    def encode(self) -> str:
        """``RGWL1:`` followed by base64url of the JSON document."""
        document = {
            "v": PROTOCOL_VERSION,
            "gw": self.gateway,
            "gfp": self.gateway_fingerprint,
            "token": self.token,
            "id": self.gateway_id,
        }
        return self.PREFIX + b64e(json.dumps(document, separators=(",", ":")).encode("utf-8"))

    @classmethod
    def decode(cls, text: str) -> LinkText:
        """Read a text made by :meth:`encode`."""
        text = "".join(text.split())
        if not text.startswith(cls.PREFIX):
            raise ProtocolError("not a link text")
        try:
            document = json.loads(b64d(text[len(cls.PREFIX) :], max_length=4096))
            if not isinstance(document, dict) or not is_version(document.get("v")):
                raise ProtocolError("link text of another version")
            return cls(
                str(document["gw"]),
                str(document.get("gfp", "")).lower(),
                str(document["token"]),
                str(document.get("id", "")),
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, RecursionError) as error:
            raise ProtocolError("link text unreadable") from error
