# SPDX-License-Identifier: GPL-3.0-or-later
"""Encrypting secrets that Rentalars has to store in the database (EML-002, AUT-006).

The password of the project mailbox and the keys for two-factor login must be
stored in a form Rentalars can read again – a hash would not do. They are
encrypted with a key derived from ``secret_key`` of the configuration file
(Fernet: AES-128 in CBC mode with an HMAC, from the ``cryptography`` library).

So a copy of the database alone – a lost backup without the configuration
file, a look into the tables – does not give away the passwords. Whoever
holds both the database and the configuration file can decrypt them; that
is unavoidable for a program that must log in to the mailbox on its own.

Changing ``secret_key`` makes the stored secrets unreadable: the mailbox
password has to be entered again, and two-factor login set up again.
Rentalars then says so instead of failing in silence (:class:`SecretUnreadableError`).
"""

from __future__ import annotations

import base64
from functools import cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


class SecretUnreadableError(Exception):
    """A stored secret cannot be decrypted – usually because ``secret_key`` changed."""


@cache
def _fernet(secret_key: str) -> Fernet:
    """The cipher for a given secret key (derived once per process)."""
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"rentalars stored secrets v1").derive(
        secret_key.encode("utf-8")
    )
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(text: str) -> str:
    """Encrypt a secret for storing; an empty text stays empty."""
    if not text:
        return ""
    return _fernet(settings.SECRET_KEY).encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Decrypt a stored secret; an empty value stays empty.

    Raises:
        SecretUnreadableError: The value was encrypted with another key.
    """
    if not token:
        return ""
    try:
        return _fernet(settings.SECRET_KEY).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as error:
        raise SecretUnreadableError(str(error)) from error
