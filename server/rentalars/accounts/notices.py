# SPDX-License-Identifier: GPL-3.0-or-later
"""A notice to the holder of an account when its login details change (AUT-030).

The requirement: a mail "your login details were changed" to the previous address, with the time and a hint on what to
do.

What is noticed
---------------
* The e-mail address of an account – its login address – changed: the mail
  goes to the *previous* address. It names the old and the new address and
  says to tell the administrators at once if it was not the holder: with the
  new address somebody else could reset the password. The new address gets
  no mail – Rentalars does not confirm addresses, and a mistyped one would
  tell a stranger about the account.
* The password changed – on "My account", or chosen after a one-time
  password –, was reset with the link from the e-mail, or an administrator
  set a one-time password: the mail goes to the current address and points
  to "Forgot your password?".

Each mail says when (the local time of the installation), by whom if it was
not the holder, and the address of the installation – in the holder's
language (:func:`rentalars.core.i18n.for_user`).

When there is no mail
---------------------
* when an account is created, and when a first password is set (the link
  of the invitation, a one-time password for an account that never had a
  password) – nothing is replaced;
* without a previous address (e-mail) or a current one (password);
* for a deactivated or expired account – checked after the change.

How
---
The mail is sent once the change is committed (``transaction.on_commit``).
A failure is logged and never undoes the change. A notice that went out is
noted in the change log of the account, which the security log shows
(AUT-022).

E-mail addresses are watched where they are stored, not on every page that
changes them: the account (``User.save``) and the person (``Person.save``,
which passes the address on to the account with a query update, AUT-026).
:func:`account_saving` and :func:`person_saving` – ``pre_save`` signals,
connected in ``accounts.apps`` – compare the new address with the account's
row in the database. A change passed from the person to the account or from
the account to the person therefore sends exactly one mail, whichever way it
was made: own personnel data and ``PATCH /people/me/profile``, the user form
and ``/users``, the person form and ``/people``, the import of people.
Passwords are noticed where they are changed (``accounts.views``,
``accounts.services.set_one_time_password``).
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

#: What changed (AUT-030). Names of changes, no secrets.
EMAIL = "email"
PASSWORD = "password"  # noqa: S105
PASSWORD_RESET = "password_reset"  # noqa: S105
ONE_TIME_PASSWORD = "one_time_password"  # noqa: S105
CHANGES = (EMAIL, PASSWORD, PASSWORD_RESET, ONE_TIME_PASSWORD)

#: The template of the mail; plain text like the other mails to users.
TEMPLATE = "accounts/email/credentials_changed.txt"


@dataclass(frozen=True)
class Notice:
    """One notice to send after the commit: what changed, when, by whom."""

    user_id: int
    change: str
    moment: datetime.datetime
    #: The name of who changed it, if not the holder; empty if the holder or unknown.
    by_name: str = ""
    #: Changed by Rentalars itself – an import, a job – rather than by a person.
    by_system: bool = False
    old_email: str = ""
    new_email: str = ""


def _normal(address: Any) -> str:
    """An address as stored on the account: trimmed, lower case; empty for none."""
    return str(address or "").strip().lower()


def _by(by: Any, user_id: int) -> tuple[str, bool]:
    """Name and "by the system" of who changed the details of account ``user_id``; nothing for the holder."""
    if by is None:
        return "", False
    if isinstance(by, str):
        return "", True
    if getattr(by, "pk", None) == user_id:
        return "", False
    return str(by), False


def credentials_changed(user: Any, change: str, *, by: Any = None, old_email: str = "", new_email: str = "") -> None:
    """Send the notice "your login details were changed" once the change is committed (AUT-030).

    Args:
        user: The account whose details changed.
        change: One of :data:`CHANGES`.
        by: Who changed them: a user (nothing is said when it is the holder),
            a text for Rentalars itself (an import, a job), or ``None`` for the
            holder or nobody known.
        old_email: For :data:`EMAIL`, the previous address – the mail goes there.
        new_email: For :data:`EMAIL`, the new address.

    Called after the change was saved, in the same transaction; the mail goes
    out after the commit, or not at all if the transaction is rolled back.
    """
    if user is None or user.pk is None:
        return
    by_name, by_system = _by(by, user.pk)
    _schedule(user.pk, change, by_name=by_name, by_system=by_system, old_email=old_email, new_email=new_email)


def _schedule(
    user_id: int, change: str, *, by_name: str = "", by_system: bool = False, old_email: str = "", new_email: str = ""
) -> None:
    """Send a notice to account ``user_id`` after the commit (see :func:`credentials_changed`)."""
    if change not in CHANGES:
        raise ValueError(change)
    if change == EMAIL and not _normal(old_email):
        return  # there is no previous address to tell
    notice = Notice(
        user_id=user_id,
        change=change,
        moment=timezone.now(),
        by_name=by_name,
        by_system=by_system,
        old_email=_normal(old_email),
        new_email=_normal(new_email),
    )
    transaction.on_commit(lambda: send_notice(notice))


def send_notice(notice: Notice) -> bool:
    """Send one notice now; return whether a mail was handed to a mail server.

    Nothing is sent for an account that is gone, deactivated or expired, or
    without the address the mail would go to. A failure is logged, never
    raised (the change it tells of is done).
    """
    from rentalars.accounts.models import User
    from rentalars.core.audit import record_event
    from rentalars.core.i18n import for_user, local_pattern
    from rentalars.core.models import CompanyProfile

    user = User.objects.filter(pk=notice.user_id).first()
    if user is None or not user.is_active or user.has_expired:
        return False
    recipient = notice.old_email if notice.change == EMAIL else _normal(user.email)
    if not recipient:
        return False
    try:
        with for_user(user):
            moment = timezone.localtime(notice.moment)
            context = {
                "user": user,
                "change": notice.change,
                "old_email": notice.old_email,
                "new_email": notice.new_email,
                "when": _("%(date)s at %(time)s")
                % {"date": moment.strftime(local_pattern("%d.%m.%Y")), "time": moment.strftime("%H:%M")},
                "by": _("Rentalars itself (automatically)") if notice.by_system else notice.by_name,
                "company_name": CompanyProfile.load().name or "Rentalars",
                "site_url": settings.RENTALARS_URL,
                "reset_url": f"{settings.RENTALARS_URL}{reverse('accounts:password_reset')}",
            }
            sent = send_mail(
                subject=_("Your login details were changed"),
                message=render_to_string(TEMPLATE, context),
                from_email=None,
                recipient_list=[recipient],
                fail_silently=False,
            )
    except Exception:
        logger.warning(
            "The notice of changed login details (%s) for user %s could not be sent.",
            notice.change,
            notice.user_id,
            exc_info=True,
        )
        return False
    if not sent:
        return False  # EML-048: no mail server – the mail log says so
    details = {"to": recipient}
    if notice.change == EMAIL:
        details.update(old=notice.old_email, new=notice.new_email)
    record_event(user, f"user.notice_{notice.change}", details)
    return True


# --- Watching the e-mail address (AUT-026, AUT-030) -------------------------------------------------


def _email_changed(user_id: int, old: str, new: str) -> None:
    """Note a changed login address of account ``user_id``, by whoever acts now (``core.audit``)."""
    from rentalars.core.audit import get_current_actor

    actor = get_current_actor()
    by_name, by_system = "", False
    if actor is not None and actor.user_id != user_id:
        by_name, by_system = ("", True) if actor.user_id is None else (actor.label, False)
    _schedule(user_id, EMAIL, by_name=by_name, by_system=by_system, old_email=old, new_email=new)


def _stored_address(user_id: int) -> str:
    """The login address of an account as the database holds it now."""
    from rentalars.accounts.models import User

    return _normal(User.objects.filter(pk=user_id).values_list("email", flat=True).first())


def _unchanged(instance: Any, new: str) -> bool:
    """Whether the address of a loaded record is the one it was loaded with – then no query is needed."""
    before = instance._audit_before()
    return before is not None and "email" in before and _normal(before["email"]) == new


def account_saving(sender: Any, instance: Any, raw: bool = False, update_fields: Any = None, **kwargs: Any) -> None:
    """``pre_save`` of an account: a changed login address is noticed to the previous one (AUT-030).

    A new account is no change. The address is compared with the row in the
    database: a change a person already passed on (``Person.save``) is not
    noticed a second time.
    """
    if raw or instance._state.adding or instance.pk is None:
        return
    if update_fields is not None and "email" not in update_fields:
        return
    new = _normal(instance.email)
    if _unchanged(instance, new):
        return
    old = _stored_address(instance.pk)
    if old != new:
        _email_changed(instance.pk, old, new)


def person_saving(sender: Any, instance: Any, raw: bool = False, **kwargs: Any) -> None:
    """``pre_save`` of a person: an address the person passes on to the account is noticed (AUT-026, AUT-030).

    ``Person.save`` writes the address into the account with a query update,
    which no signal sees – so it is caught here, against the account's row.
    When the account itself is being saved (``User.save`` keeps its person
    in step), the row holds the new address already and nothing is sent
    twice. A new or anonymised person is no change.
    """
    if raw or instance._state.adding or not instance.user_id or instance.anonymised_at:
        return
    new = _normal(instance.email)
    if _unchanged(instance, new):
        return
    old = _stored_address(instance.user_id)
    if old != new:
        _email_changed(instance.user_id, old, new)


def connect() -> None:
    """Connect the watching of e-mail addresses (called by ``accounts.apps``)."""
    from django.db.models.signals import pre_save

    pre_save.connect(account_saving, sender="accounts.User", dispatch_uid="accounts.notices.account")
    pre_save.connect(person_saving, sender="personnel.Person", dispatch_uid="accounts.notices.person")
