# SPDX-License-Identifier: GPL-3.0-or-later
"""Artificial intelligence in Rentalars (EML-040, EML-044, ADM-017).

* A summary of a project's correspondence – by a language model on this
  machine (the "local AI" the operator installs with ``sudo rentalars ai
  install``) or by a provider an administrator chose – and, always available,
  a short overview without AI (:mod:`rentalars.ai.overview`).
* An interface to OpenAI-compatible servers for further uses (ADM-017): a
  reply draft in the mail form; off until an administrator chooses a provider.
* Every call is logged without its content (:class:`rentalars.ai.models.AICall`).
"""
