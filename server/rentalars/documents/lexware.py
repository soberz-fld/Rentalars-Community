# SPDX-License-Identifier: GPL-3.0-or-later
"""Handing invoices and cancellations to Lexware Office (DOK-011).

Lexware Office (formerly lexoffice) has a public REST API at
``https://api.lexware.io`` (developer documentation:
https://developers.lexware.io/docs/). Every request carries the API key of
the account as ``Authorization: Bearer …``; the key is created in Lexware
Office by an administrator of the account (Add-ons → Public API) and stored
here encrypted (``AccountingSettings``). The API takes at most two requests
per second per key and answers more with 429.

What Rentalars writes
---------------------
An invoice made in Rentalars already has its number, its PDF and its
XRechnung. In Lexware Office it therefore becomes a bookkeeping **voucher**
(``POST /v1/vouchers``), not an invoice of Lexware Office – that would get a
second number and a second PDF:

* ``type`` ``salesinvoice``; a cancellation (any document whose total is
  negative) ``salescreditnote``. The amounts are positive, the type says
  the direction;
* ``voucherNumber`` the number of Rentalars; ``voucherDate`` its date,
  ``shippingDate`` the end of the period of service, ``dueDate`` the due
  date of an invoice;
* ``taxType`` ``net``: one voucher item per tax rate with the net amount
  (``amount``), the tax (``taxAmount``), the rate (``taxRatePercent``) and
  the posting category (``categoryId``, "Einnahmen" unless set otherwise per
  rate). These are the amounts per tax rate of the stored document – the
  same the PDF and the XRechnung show (``content.TaxShare``) – so the sums
  ``totalGrossAmount`` and ``totalTaxAmount`` agree with the items to the
  cent, as Lexware Office requires;
* ``contactId`` of the customer, or ``useCollectiveContact`` when the
  settings say so.

Then the PDF goes to the voucher: ``POST /v1/vouchers/{id}/files``
(``multipart/form-data``, field ``file``).

The customer
------------
A customer is looked for by its customer number (``GET /v1/contacts?number=…
&customer=true``): customers imported from a contact export of Lexware
(IMP-013) have the number Lexware Office gave them. A contact found that way
is taken only if its name agrees with the customer in Rentalars – Lexware
Office numbers its contacts on its own, and a customer created in Rentalars
may meet a different customer with the same number there. Then the handing
over stops and says so; it can be repeated with "create as new contact".
If no contact is found, one is created (``POST /v1/contacts``, company or
person, billing address, e-mail address, phone, VAT ID and tax number). The
customer number of a new contact is given by Lexware Office and cannot be
set. The ID of the contact is kept on the customer, so that the next invoice
goes to the same contact.

Nothing twice
-------------
One :class:`~rentalars.documents.models.LexwareTransfer` per document notes
what was handed over. Before a voucher is created, Lexware Office is asked
whether it has one with this number already (``GET /v1/voucherlist``); if
so, and its amount agrees, that one is taken. The voucher ID is stored as
soon as it is known, so that another attempt after an error only uploads the
PDF; Lexware Office also refuses the same file twice for the same voucher.
Only one attempt per document runs at a time.

All HTTP goes through :func:`_send`, with the standard library only. The
tests replace it; they never reach the network.
"""

from __future__ import annotations

import datetime
import http.client
import json
import logging
import re
import secrets
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars import __version__
from rentalars.core.audit import record_event
from rentalars.core.crypto import SecretUnreadableError
from rentalars.core.i18n import LocalText
from rentalars.documents.content import ZERO, DocumentContent, from_json
from rentalars.documents.models import (
    AccountingSettings,
    Document,
    LexwareTransfer,
    TransferState,
)

logger = logging.getLogger(__name__)

#: The address of the public API of Lexware Office.
BASE_URL = "https://api.lexware.io"

#: Seconds to wait for an answer.
TIMEOUT = 20

#: The largest answer read (5 MB); a voucher list of 250 entries is far smaller.
MAX_BYTES = 5 * 1024 * 1024

#: Lexware Office takes at most two requests per second per API key.
MIN_INTERVAL = 0.5

#: How long to wait before asking again after "429 Too Many Requests"; Lexware sends no Retry-After.
RETRY_WAITS = (1.0, 2.0, 4.0)

#: A handing over still "running" after this long is taken to be lost and may be started again.
STALE_AFTER = datetime.timedelta(minutes=15)

USER_AGENT = f"Rentalars/{__version__} (accounting)"

#: Kinds of errors, kept with a failed handing over.
ERROR_CODES = (
    "auth",
    "rate_limit",
    "rejected",
    "contact_conflict",
    "voucher_conflict",
    "unreachable",
    "server",
    "other",
)


class LexwareError(Exception):
    """Lexware Office could not be asked or refused something.

    ``str(error)`` is a German text for the person who handed over;
    ``code`` one of :data:`ERROR_CODES`.
    """

    def __init__(self, message: str, *, code: str = "other", status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


# --- HTTP -------------------------------------------------------------------------------------------


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """The API does not redirect; a redirection is handed back as an answer instead of being followed."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Do not follow – the API key must not go anywhere else."""
        return None


_OPENER = urllib.request.build_opener(_NoRedirects)

#: Replaced in the tests, which must not wait.
_sleep = time.sleep

_turn = threading.Lock()
_last_request = 0.0


def _wait_turn() -> None:
    """Keep at least :data:`MIN_INTERVAL` between two requests of this process."""
    global _last_request
    with _turn:
        pause = _last_request + MIN_INTERVAL - time.monotonic()
        if pause > 0:
            _sleep(pause)
        _last_request = time.monotonic()


def _network_problem(error: BaseException) -> str:
    reason: Any = getattr(error, "reason", error)
    if isinstance(reason, TimeoutError | socket.timeout):
        text = _("no answer within %(seconds)d seconds") % {"seconds": TIMEOUT}
    elif isinstance(reason, socket.gaierror):
        text = _("the server name is unknown")
    elif isinstance(reason, ssl.SSLError | ssl.CertificateError):
        text = _("the secure connection failed (certificate)")
    else:
        text = _("the connection failed")
    return _("Lexware Office cannot be reached: %(problem)s.") % {"problem": text}


def _read(response: Any) -> bytes:
    data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise LexwareError(_("The answer of Lexware Office is too large."), code="server")
    return data


def _send(method: str, url: str, *, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    """One exchange with Lexware Office: the status and the body of the answer.

    The only place that touches the network; the tests replace it.

    Raises:
        LexwareError: No answer could be had at all.
    """
    prepared = urllib.request.Request(url, data=body, method=method, headers=headers)  # noqa: S310 - fixed https address
    try:
        with _OPENER.open(prepared, timeout=TIMEOUT) as response:
            return response.status, _read(response)
    except urllib.error.HTTPError as error:
        try:
            data = _read(error)
        except (OSError, http.client.HTTPException, LexwareError):
            data = b""
        finally:
            error.close()
        return error.code, data
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as error:
        raise LexwareError(_network_problem(error), code="unreachable") from error


def _problem_text(data: bytes) -> str:
    """What Lexware Office says is wrong, from both of its error formats, at most 500 characters.

    The current format has ``message`` and ``details`` (``field``, ``message``);
    older endpoints answer with an ``IssueList`` (``source``, ``i18nKey``).
    """
    try:
        answer = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return data.decode("utf-8", "replace").strip()[:300]
    parts: list[str] = []
    if isinstance(answer, dict):
        for issue in answer.get("IssueList") or []:
            if isinstance(issue, dict):
                parts.append(": ".join(str(issue[key]) for key in ("source", "i18nKey") if issue.get(key)))
        for detail in answer.get("details") or []:
            if isinstance(detail, dict):
                message = detail.get("message") or detail.get("violation") or ""
                parts.append(f"{detail['field']}: {message}" if detail.get("field") else str(message))
        if not any(parts) and answer.get("message"):
            parts.append(str(answer["message"]))
    return "; ".join(part for part in parts if part)[:500]


def _failure(status: int, data: bytes) -> LexwareError:
    """The error for an answer that is not a success."""
    if status == 401:
        return LexwareError(
            _("Lexware Office refused the API key. Check it under Settings → Accounting."), code="auth", status=status
        )
    if status in (402, 403):
        return LexwareError(
            _(
                "Lexware Office does not allow this with this API key. Check the rights of the key and whether the "
                "plan of the account includes bookkeeping."
            ),
            code="auth",
            status=status,
        )
    if status == 429:
        return LexwareError(
            _("Lexware Office takes at most two requests per second and refused further ones. Try again in a moment."),
            code="rate_limit",
            status=status,
        )
    if status >= 500:
        return LexwareError(
            _("Lexware Office answered with error %(status)d. Try again later.") % {"status": status},
            code="server",
            status=status,
        )
    problem = _problem_text(data) or str(status)
    return LexwareError(
        _("Lexware Office refused the data: %(problem)s") % {"problem": problem}, code="rejected", status=status
    )


def _multipart(name: str, content: bytes, content_type: str) -> tuple[bytes, str]:
    """A ``multipart/form-data`` body with the one field ``file``."""
    boundary = f"rentalars-{secrets.token_hex(12)}"
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "beleg.pdf"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("ascii")
    return head + content + f"\r\n--{boundary}--\r\n".encode("ascii"), f"multipart/form-data; boundary={boundary}"


class LexwareClient:
    """The few calls of the Lexware Office API that DOK-011 needs."""

    def __init__(self, api_key: str, *, base_url: str = BASE_URL) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def call(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        payload: Any = None,
        upload: tuple[str, bytes, str] | None = None,
    ) -> Any:
        """Send one request and return the answer as data.

        Waits for its turn (two requests per second) and asks again after
        "429 Too Many Requests", as often as :data:`RETRY_WAITS` says.

        Raises:
            LexwareError: The request failed; the text says why.
        """
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query, safe=",")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif upload is not None:
            body, headers["Content-Type"] = _multipart(*upload)
        for attempt in range(len(RETRY_WAITS) + 1):
            _wait_turn()
            status, data = _send(method, url, headers=headers, body=body)
            if status != 429 or attempt == len(RETRY_WAITS):
                break
            _sleep(RETRY_WAITS[attempt])
        if not 200 <= status < 300:
            raise _failure(status, data)
        if not data.strip():
            return {}
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LexwareError(_("Lexware Office answered with something that is not JSON."), code="server") from error

    # --- The calls ---

    def profile(self) -> dict[str, Any]:
        """The account the key belongs to, with ``companyName``, ``taxType`` and ``smallBusiness``."""
        return self.call("GET", "/v1/profile")

    def income_categories(self) -> list[dict[str, str]]:
        """The posting categories for income (``GET /v1/posting-categories``, ``type`` "income")."""
        answer = self.call("GET", "/v1/posting-categories")
        return [
            {"id": str(category.get("id", "")), "name": str(category.get("name", ""))}
            for category in (answer if isinstance(answer, list) else [])
            if isinstance(category, dict) and category.get("type") == "income" and category.get("id")
        ]

    def vouchers_numbered(self, number: str) -> list[dict[str, Any]]:
        """Sales vouchers of any state with exactly this number (``GET /v1/voucherlist``)."""
        answer = self.call(
            "GET",
            "/v1/voucherlist",
            query={
                "voucherType": "salesinvoice,salescreditnote",
                "voucherStatus": "any",
                "voucherNumber": number,
                "size": "250",
            },
        )
        content = answer.get("content", []) if isinstance(answer, dict) else []
        return [voucher for voucher in content if isinstance(voucher, dict) and voucher.get("voucherNumber") == number]

    def create_voucher(self, body: dict[str, Any]) -> str:
        """Create a voucher; returns its ID."""
        return _id_of(self.call("POST", "/v1/vouchers", payload=body))

    def upload_voucher_file(self, voucher_id: str, name: str, content: bytes) -> str:
        """Attach a PDF to a voucher; returns the ID of the file if Lexware Office names it."""
        path = f"/v1/vouchers/{urllib.parse.quote(voucher_id, safe='')}/files"
        answer = self.call("POST", path, upload=(name, content, "application/pdf"))
        return str(answer.get("id", "")) if isinstance(answer, dict) else ""

    def customer_contacts_numbered(self, number: int) -> list[dict[str, Any]]:
        """Contacts with the customer role and this customer number (``GET /v1/contacts``)."""
        answer = self.call("GET", "/v1/contacts", query={"number": str(number), "customer": "true"})
        content = answer.get("content", []) if isinstance(answer, dict) else []
        return [
            contact
            for contact in content
            if isinstance(contact, dict)
            and str(((contact.get("roles") or {}).get("customer") or {}).get("number", "")) == str(number)
        ]

    def create_contact(self, body: dict[str, Any]) -> str:
        """Create a contact; returns its ID."""
        return _id_of(self.call("POST", "/v1/contacts", payload=body))


def _id_of(answer: Any) -> str:
    if isinstance(answer, dict) and answer.get("id"):
        return str(answer["id"])
    raise LexwareError(_("Lexware Office did not name the new record."), code="server")


# --- What is sent --------------------------------------------------------------------------------


def _amount(value: Decimal) -> float:
    """An amount as Lexware Office wants it: a number with two decimals."""
    return float(value.quantize(Decimal("0.01")))


def _percent(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _country_code(country: str) -> str:
    from rentalars.documents.xrechnung import _country_code as code

    return code(country)


def voucher_body(
    document: Document, content: DocumentContent, accounting: AccountingSettings, *, contact_id: str
) -> dict[str, Any]:
    """The voucher of an invoice or cancellation (DOK-011), see the description of the module.

    ``contact_id`` empty: the voucher goes to the collective contact.
    """
    # A final invoice books what the advance and partial invoices did not (they were handed over themselves).
    booked_gross, booked_tax = content.booked_gross_total, content.booked_tax_total
    sign = Decimal("-1") if booked_gross < ZERO else Decimal("1")
    items = []
    for share in content.booked_taxes:
        net, tax = share.net * sign, share.tax * sign
        if net == ZERO and tax == ZERO:
            continue
        items.append(
            {
                "amount": _amount(net),
                "taxAmount": _amount(tax),
                "taxRatePercent": _percent(share.percent),
                "categoryId": accounting.lexware_category_for(share.percent),
            }
        )
    if not items and content.taxes:  # a final invoice that adds nothing: a voucher needs one item all the same
        share = content.taxes[0]
        items.append(
            {
                "amount": _amount(ZERO),
                "taxAmount": _amount(ZERO),
                "taxRatePercent": _percent(share.percent),
                "categoryId": accounting.lexware_category_for(share.percent),
            }
        )
    if content.cancels_number and content.project.get("number") and content.billing_type == "credit":
        remark = _("Credit for invoice %(number)s. Project %(project)s “%(name)s”") % {
            "number": content.cancels_number,
            "project": content.project.get("number", ""),
            "name": content.project.get("name", ""),
        }
    elif content.cancels_number and content.project.get("number"):
        remark = _("Cancels invoice %(number)s. Project %(project)s “%(name)s”") % {
            "number": content.cancels_number,
            "project": content.project.get("number", ""),
            "name": content.project.get("name", ""),
        }
    elif content.project.get("number"):
        remark = _("Project %(project)s “%(name)s”") % {
            "project": content.project.get("number", ""),
            "name": content.project.get("name", ""),
        }
    else:
        # Free outgoing documents: made in Accounting, without a project – the reference, if there is one.
        remark = content.reference or _("Without project")
        if content.cancels_number:
            remark = _("Cancels invoice %(number)s.") % {"number": content.cancels_number} + " " + remark
    body: dict[str, Any] = {
        "type": "salesinvoice" if sign > ZERO else "salescreditnote",
        "voucherNumber": document.number,
        "voucherDate": content.issued_on.isoformat(),
        "totalGrossAmount": _amount(booked_gross * sign),
        "totalTaxAmount": _amount(booked_tax * sign),
        "taxType": "net",
        "useCollectiveContact": not contact_id,
        "remark": f"{remark} – Rentalars",
        "voucherItems": items,
    }
    if contact_id:
        body["contactId"] = contact_id
    if content.service_end:
        body["shippingDate"] = content.service_end.isoformat()
    if content.due_on:
        body["dueDate"] = content.due_on.isoformat()
    return body


def _split_name(name: str) -> tuple[str, str]:
    """First and last name of a person written in one field: "Anna Maria Beispiel" → ("Anna Maria", "Beispiel")."""
    first, _space, last = name.strip().rpartition(" ")
    return first, last or name.strip()


def contact_body(customer: Any) -> dict[str, Any]:
    """A new contact with the customer role for a customer of Rentalars (DOK-011)."""
    from rentalars.customers.models import CustomerKind

    body: dict[str, Any] = {"version": 0, "roles": {"customer": {}}}
    if customer.kind == CustomerKind.PRIVATE:
        first, last = _split_name(customer.name)
        body["person"] = {"firstName": first, "lastName": last} if first else {"lastName": last}
    else:
        company: dict[str, Any] = {"name": customer.name}
        if customer.tax_number:
            company["taxNumber"] = customer.tax_number
        if customer.vat_id:
            company["vatRegistrationId"] = customer.vat_id
        primary = customer.primary_contact
        if primary is not None and primary.name.strip():
            # KND-004: the stored first and last name; contacts saved by old code are split as before.
            first, last = (primary.first_name, primary.last_name) if primary.last_name else _split_name(primary.name)
            person: dict[str, Any] = {"lastName": last, "primary": True}
            if first:
                person["firstName"] = first
            if primary.salutation:
                person["salutation"] = primary.salutation[:25]
            if primary.email:
                person["emailAddress"] = primary.email
            if primary.phone:
                person["phoneNumber"] = primary.phone
            company["contactPersons"] = [person]
        body["company"] = company
    if customer.street or customer.city:
        address = {"countryCode": _country_code(customer.country)}
        for key, value in (
            ("supplement", customer.name_addition),
            ("street", customer.street),
            ("zip", customer.postal_code),
            ("city", customer.city),
        ):
            if value:
                address[key] = value
        body["addresses"] = {"billing": [address]}
    if customer.email:
        body["emailAddresses"] = {"business": [customer.email]}
    if customer.phone:
        body["phoneNumbers"] = {"business": [customer.phone]}
    body["note"] = _("Created by Rentalars for customer %(number)s.") % {"number": customer.number}
    return body


def _contact_name(contact: dict[str, Any]) -> str:
    company = contact.get("company") or {}
    if company.get("name"):
        return str(company["name"])
    person = contact.get("person") or {}
    return " ".join(str(part) for part in (person.get("firstName"), person.get("lastName")) if part)


def same_name(first: str, second: str) -> bool:
    """Whether two names mean the same customer – as the duplicate check of KND-008 compares them."""
    from rentalars.customers.services import normalised_name

    one, other = normalised_name(first or ""), normalised_name(second or "")
    if not one or not other:
        return False
    if one == other:
        return True
    shorter, longer = sorted((one, other), key=len)
    return len(shorter) >= 8 and longer.startswith(shorter)


# --- Handing over --------------------------------------------------------------------------------


def _client(accounting: AccountingSettings) -> LexwareClient:
    try:
        key = accounting.lexware_api_key
    except SecretUnreadableError as error:
        raise LexwareError(
            _(
                "The stored API key of Lexware Office cannot be read any more – the secret key of the configuration "
                "was changed. Enter the API key again."
            ),
            code="auth",
        ) from error
    if not key:
        raise LexwareError(_("No API key for Lexware Office is entered."), code="auth")
    return LexwareClient(key)


@dataclass
class CheckResult:
    """What "Check connection" found out."""

    organization: str
    tax_type: str
    small_business: bool
    categories: list[dict[str, str]] = field(default_factory=list)


def check_connection() -> CheckResult:
    """Ask Lexware Office for the account and its income categories, and keep them (DOK-011).

    Raises:
        LexwareError: The key is missing or refused, or Lexware Office cannot be reached.
    """
    accounting = AccountingSettings.load()
    client = _client(accounting)
    profile = client.profile()
    categories = client.income_categories()
    accounting.lexware_organization = str(profile.get("companyName") or "")[:200]
    accounting.lexware_category_choices = categories
    accounting.lexware_checked_at = timezone.now()
    accounting.save(update_fields=["lexware_organization", "lexware_category_choices", "lexware_checked_at"])
    return CheckResult(
        organization=accounting.lexware_organization,
        tax_type=str(profile.get("taxType") or ""),
        small_business=bool(profile.get("smallBusiness")),
        categories=categories,
    )


def transfer_of(document: Document) -> LexwareTransfer | None:
    """The handing over of a document, if there is one."""
    try:
        return document.lexware_transfer
    except LexwareTransfer.DoesNotExist:
        return None


def request_transfer(
    document: Document, *, user: Any = None, automatic: bool = False, new_contact: bool = False
) -> LexwareTransfer:
    """Hand a document to Lexware Office in the background (DOK-011).

    Args:
        document: An invoice or a cancellation.
        user: Who asks; told when the task is done. An automatic handing
            over tells this user only if it fails.
        automatic: Started because the document was just made.
        new_contact: Create the customer as a new contact in Lexware Office
            instead of looking for it by its customer number.

    Raises:
        ValidationError: Switched off – handing over, or invoices altogether
            (DOK-014) –, no key, not an invoice, handed over already or on
            the way.
    """
    from rentalars.core.jobs import start_job
    from rentalars.documents.services import check_invoices_enabled

    check_invoices_enabled()
    accounting = AccountingSettings.load()
    if not accounting.lexware_enabled:
        raise ValidationError(
            _("Handing over to Lexware Office is switched off. Switch it on under Settings → Accounting.")
        )
    if not accounting.has_lexware_api_key:
        raise ValidationError(_("No API key for Lexware Office is entered."))
    if not document.is_bookable:
        raise ValidationError(_("Only invoices and cancellations go to Lexware Office."))
    now = timezone.now()
    with transaction.atomic():
        transfer, created = LexwareTransfer.objects.select_for_update().get_or_create(
            document=document, defaults={"requested_by": user if getattr(user, "pk", None) else None}
        )
        if transfer.is_done:
            raise ValidationError(_("%(number)s is in Lexware Office already.") % {"number": document.number})
        if not created and transfer.is_pending and transfer.updated_at > now - STALE_AFTER:
            raise ValidationError(
                _("%(number)s is being handed to Lexware Office already.") % {"number": document.number}
            )
        LexwareTransfer.objects.filter(pk=transfer.pk).update(
            state=TransferState.QUEUED,
            requested_at=now,
            requested_by=user if getattr(user, "pk", None) else None,
            updated_at=now,
        )
        params: dict[str, Any] = {"transfer": transfer.pk}
        if new_contact:
            params["new_contact"] = True
        if automatic and getattr(user, "pk", None):
            params["notify"] = user.pk
        title = _("Hand %(document)s to Lexware Office") % {"document": f"{document.title} {document.number}"}
        job = start_job("lexware", params, user=None if automatic else user, title=title)
        LexwareTransfer.objects.filter(pk=transfer.pk).update(job=job)
    transfer.refresh_from_db()
    return transfer


def transfer_automatically(document: Document, *, user: Any = None) -> None:
    """DOK-011: hand a new invoice or cancellation over at once, if the settings say so.

    Never stops the document from being made: a problem is logged, and the
    document can be handed over by hand.
    """
    if not document.is_bookable:
        return
    accounting = AccountingSettings.load()
    if not (accounting.lexware_enabled and accounting.lexware_automatic and accounting.has_lexware_api_key):
        return
    try:
        request_transfer(document, user=user, automatic=True)
    except Exception:
        logger.exception("Document %s could not be handed to Lexware Office.", document.number)


def perform_transfer(transfer: LexwareTransfer, *, new_contact: bool = False, job: Any = None) -> LexwareTransfer:
    """Hand one document over now; what was done before is not done again (DOK-011).

    Raises:
        LexwareError: Lexware Office refused or could not be reached; the
            handing over is marked as failed with the reason.
    """
    now = timezone.now()
    claim = Q(state__in=[TransferState.QUEUED, TransferState.FAILED]) | Q(
        state=TransferState.RUNNING, updated_at__lt=now - STALE_AFTER
    )
    if job is not None:
        # The same task started once more after a restart takes up its own work.
        claim |= Q(state=TransferState.RUNNING, job_id=job.pk)
    claimed = (
        LexwareTransfer.objects.filter(pk=transfer.pk)
        .filter(claim)
        .update(state=TransferState.RUNNING, attempts=F("attempts") + 1, updated_at=now, error="", error_code="")
    )
    transfer.refresh_from_db()
    if not claimed:
        if transfer.is_done:
            return transfer
        raise LexwareError(
            _("%(number)s is being handed to Lexware Office already.") % {"number": transfer.document.number}
        )
    try:
        _hand_over(transfer, new_contact=new_contact)
    except Exception as error:
        if isinstance(error, LexwareError):
            message, code = str(error), error.code
        else:
            logger.exception("Handing over %s to Lexware Office failed.", transfer.document.number)
            message, code = _("Unexpected error: %(error)s") % {"error": error}, "other"
        LexwareTransfer.objects.filter(pk=transfer.pk).update(
            state=TransferState.FAILED, error=message[:2000], error_code=code, updated_at=timezone.now()
        )
        transfer.refresh_from_db()
        raise
    transfer.refresh_from_db()
    return transfer


def _note(transfer: LexwareTransfer, **values: Any) -> None:
    """Store progress at once, so that a later attempt does not do it again."""
    LexwareTransfer.objects.filter(pk=transfer.pk).update(updated_at=timezone.now(), **values)
    for name, value in values.items():
        setattr(transfer, name, value)


def _hand_over(transfer: LexwareTransfer, *, new_contact: bool) -> None:
    accounting = AccountingSettings.load()
    if not accounting.lexware_enabled:
        raise LexwareError(_("Handing over to Lexware Office is switched off."), code="other")
    client = _client(accounting)
    document = Document.objects.select_related("project", "customer").get(pk=transfer.document_id)
    content = from_json(document.content)
    if not transfer.voucher_id:
        existing = client.vouchers_numbered(document.number)
        if existing:
            voucher = existing[0]
            _check_amount(voucher, content, document)
            _note(transfer, voucher_id=str(voucher.get("id", "")))
        else:
            contact_id = (
                ""
                if accounting.lexware_collective_contact
                else _contact_for(client, document, content, new_contact=new_contact)
            )
            _note(transfer, contact_id=contact_id)
            voucher_id = client.create_voucher(voucher_body(document, content, accounting, contact_id=contact_id))
            _note(transfer, voucher_id=voucher_id)
    if not transfer.pdf_uploaded:
        with document.file.open("rb") as handle:
            pdf = handle.read()
        client.upload_voucher_file(transfer.voucher_id, document.file_name, pdf)
        _note(transfer, pdf_uploaded=True)
    _note(transfer, state=TransferState.DONE, transferred_at=timezone.now(), error="", error_code="")
    record_event(
        document.project or document.customer,
        "document.transferred",
        {"kind": document.get_kind_display(), "number": document.number, "to": "Lexware Office"},
    )


def _check_amount(voucher: dict[str, Any], content: DocumentContent, document: Document) -> None:
    """A voucher with the same number must be this document: same total (DOK-011)."""
    total = voucher.get("totalAmount")
    if total is None:
        return
    try:
        found = abs(Decimal(str(total)))
    except InvalidOperation:
        return
    if found != abs(content.gross_total):
        raise LexwareError(
            _(
                "Lexware Office has a voucher %(number)s already, over %(found)s instead of %(expected)s. Check it "
                "there; Rentalars does not create a second one."
            )
            % {
                "number": document.number,
                "found": f"{found:.2f}".replace(".", ","),
                "expected": f"{abs(content.gross_total):.2f}".replace(".", ","),
            },
            code="voucher_conflict",
        )


def _contact_for(client: LexwareClient, document: Document, content: DocumentContent, *, new_contact: bool) -> str:
    """The contact of the customer in Lexware Office: known, found by its number, or created."""
    from rentalars.customers.models import Customer

    customer = None
    if content.customer_number:
        customer = Customer.objects.filter(number=content.customer_number).first()
    customer = customer or document.customer or (document.project.customer if document.project_id else None)
    if customer is None:
        raise LexwareError(_("The document names no customer."))
    if customer.lexware_contact_id and not new_contact:
        return customer.lexware_contact_id
    contact_id = ""
    if not new_contact and customer.number.isdigit():
        found = client.customer_contacts_numbered(int(customer.number))
        if found:
            name = _contact_name(found[0])
            if not same_name(name, customer.name):
                raise LexwareError(
                    _(
                        "In Lexware Office, customer number %(number)s belongs to “%(other)s”, in Rentalars to "
                        "“%(name)s”. If they are different customers, hand over again and have the customer created "
                        "as a new contact."
                    )
                    % {"number": customer.number, "other": name, "name": customer.name},
                    code="contact_conflict",
                )
            contact_id = str(found[0].get("id", ""))
    if not contact_id:
        contact_id = client.create_contact(contact_body(customer))
    Customer.objects.filter(pk=customer.pk).update(lexware_contact_id=contact_id)
    return contact_id


def run_transfer_job(job: Any) -> str:
    """The background task "lexware" (NFA-041): hand one document over (DOK-011)."""
    from rentalars.documents.services import invoices_enabled

    transfer = LexwareTransfer.objects.select_related("document").get(pk=job.params["transfer"])
    if not invoices_enabled() or not AccountingSettings.load().lexware_enabled:
        # A transfer queued before "Use Rentalars as accounting software" (or the handing over) was switched
        # off must not go out any more. It stays on the list as failed and can be started again once it is on.
        message = _("Bookkeeping or the handing over to Lexware Office was switched off after this was queued.")
        LexwareTransfer.objects.filter(pk=transfer.pk, state=TransferState.QUEUED).update(
            state=TransferState.FAILED, error=message, error_code="switched_off", updated_at=timezone.now()
        )
        error = LexwareError(message, code="switched_off")
        _tell_about_failure(job, transfer, error)
        raise error
    try:
        perform_transfer(transfer, new_contact=bool(job.params.get("new_contact")), job=job)
    except Exception as error:
        _tell_about_failure(job, transfer, error)
        raise
    return _("%(document)s is in Lexware Office now.") % {
        "document": f"{transfer.document.title} {transfer.document.number}"
    }


def _tell_about_failure(job: Any, transfer: LexwareTransfer, error: Exception) -> None:
    """An automatic handing over tells whoever made the document when it fails – nobody else waits for it."""
    user_id = job.params.get("notify")
    if not user_id or job.created_by_id:
        return
    from django.urls import reverse

    from rentalars.accounts.models import User
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    document = transfer.document
    notify(
        [User.objects.filter(pk=user_id).first()],
        Kind.JOB_FINISHED,
        LocalText(
            gettext_lazy("Not handed to Lexware Office: %(document)s"), document=f"{document.title} {document.number}"
        ),
        body=str(error)[:500],
        url=reverse("documents:list", args=[document.project_id])
        if document.project_id
        else reverse("documents:outgoing"),
        project=document.project,
    )
