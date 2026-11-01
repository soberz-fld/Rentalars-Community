# SPDX-License-Identifier: GPL-3.0-or-later
"""Telling that system mails cannot go out: no mail server is set up (EML-048).

Without a mailbox with the role "system" and without ``host`` in ``[email]``
of the configuration, Django only writes system mails into the log of the
server – the sender is then ``rentalars@localhost``, the default of the
configuration file, and nothing arrives anywhere. The mail log notes such a
mail as "not sent – no mail server set up" (``mail.backends``), and the
places that send – the test mail of the self-check, invitations – say so
with :func:`warn_without_server` and point to Einstellungen → Postfächer.
Answers of the API that send a mail say ``"sent": false`` with the
``reason`` (:func:`mail_state`).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext as _

from rentalars.mail.mailboxes import has_mail_server


def settings_link() -> SafeString:
    """A link to the mailboxes in the settings, named as the navigation names it."""
    return format_html(
        '<a href="{}">{} → {}</a>', reverse("mail:settings"), _("Settings"), _("Mailboxes and signature")
    )


def not_sent_text() -> SafeString:
    """The warning for a mail that did not go out, with the way to set up a mail server (EML-048)."""
    return format_html(
        "{} {}",
        _("Not sent – no mail server set up."),
        format_html(
            _("Set up a mailbox for the system mails under {link}, or a mail server in the configuration."),
            link=settings_link(),
        ),
    )


def warn_without_server(request: HttpRequest) -> bool:
    """Add the warning to the page if system mails cannot go out; return whether it was added (EML-048)."""
    if has_mail_server():
        return False
    messages.warning(request, not_sent_text())
    return True


def request_goes_by_mail(line: Any) -> bool:
    """Whether asking a crew line sends a mail: the request with buttons, or the notification by mail (EML-048).

    PER-032: the request mail goes to the person's address when answers by
    mail are possible; otherwise the notification goes by mail if the
    person's account wants deployment requests by mail.
    """
    from rentalars.mail.crew_answers import mailbox_for_request
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import choice

    if mailbox_for_request(line) is not None:
        return True
    account = getattr(line.person, "user", None) if line.person_id else None
    if account is None or not account.is_active or not account.email:
        return False
    return choice(account, Kind.DEPLOYMENT_REQUEST)[1]


def not_sent_reason() -> str:
    """The reason in an API answer when a mail could not go out (EML-048)."""
    return _("Not sent – no mail server set up.")


def mail_state(*, sends_mail: bool = True) -> dict[str, Any]:
    """What an API answer says about a mail it should have sent: ``sent`` and, if not, ``reason`` (EML-048).

    Args:
        sends_mail: Whether the action sends a mail at all; without one ``sent`` is ``null``.
    """
    if not sends_mail:
        return {"sent": None, "reason": ""}
    if has_mail_server():
        return {"sent": True, "reason": ""}
    return {"sent": False, "reason": not_sent_reason()}
