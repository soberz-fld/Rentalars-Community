# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in for the API of Lexware Office in the tests (DOK-011): no request reaches the network.

:class:`FakeLexware` replaces ``rentalars.documents.lexware._send`` and keeps
contacts, vouchers and files like Lexware Office would. It checks every
voucher and contact it receives against the published format
(developers.lexware.io: vouchers, contacts, files) and answers a wrong one
with 400 and the error format of Lexware Office – so the tests check that the
bodies Rentalars builds would be accepted.

Use it as a context manager::

    with FakeLexware() as lexware:
        ...
        lexware.requests   # what Rentalars sent
        lexware.fail(401)  # the next answer is an error
"""

from __future__ import annotations

import datetime
import json
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from rentalars.documents.models import AccountingSettings

#: The tax rates Lexware Office takes for vouchers.
TAX_RATES = {0, 5, 7, 16, 19}

#: Fields of a voucher that are set by Lexware Office and must not be sent.
READ_ONLY = {"id", "organizationId", "voucherStatus", "createdDate", "updatedDate", "files"}

INCOME = "8f8664a1-fd86-11e1-a21f-0800200c9a66"
SERVICE = "8f8664a0-fd86-11e1-a21f-0800200c9a66"
TAX_FREE_EU = "9075a4e3-66de-4795-a016-3889feca0d20"


@dataclass
class SentRequest:
    """One request as Lexware Office would have received it."""

    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: bytes | None

    @property
    def json(self) -> Any:
        """The body as data."""
        return json.loads(self.body or b"null")


@dataclass
class FakeLexware:
    """Contacts, vouchers and files of one Lexware Office account."""

    api_key: str = "lexware-test-key-0123456789abcdef"
    company: str = "Licht & Ton GmbH"
    requests: list[SentRequest] = field(default_factory=list)
    contacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    vouchers: dict[str, dict[str, Any]] = field(default_factory=dict)
    files: dict[str, list[tuple[str, bytes]]] = field(default_factory=dict)
    waits: list[float] = field(default_factory=list)
    _forced: list[tuple[int, Any]] = field(default_factory=list)
    _next_number: int = 20001

    # --- Set-up ---

    def __enter__(self) -> FakeLexware:
        self._patches = [
            mock.patch("rentalars.documents.lexware._send", self),
            mock.patch("rentalars.documents.lexware._sleep", self.waits.append),
            # The clock of the requests starts afresh: no wait before the first request of a test.
            mock.patch("rentalars.documents.lexware._last_request", 0.0),
        ]
        for patch in self._patches:
            patch.start()
        return self

    def __exit__(self, *exc: object) -> None:
        for patch in self._patches:
            patch.stop()

    @staticmethod
    def switch_on(*, automatic: bool = False, collective: bool = False, key: str | None = None) -> AccountingSettings:
        """Switch handing over on, with the key of this account."""
        accounting = AccountingSettings.load()
        accounting.set_lexware_api_key(key or FakeLexware.api_key)
        accounting.lexware_enabled = True
        accounting.lexware_automatic = automatic
        accounting.lexware_collective_contact = collective
        accounting.save()
        return accounting

    def add_contact(self, number: int, *, company: str = "", first: str = "", last: str = "") -> str:
        """A contact that exists in Lexware Office already, e.g. from before Rentalars."""
        contact_id = str(uuid.uuid4())
        contact: dict[str, Any] = {"id": contact_id, "version": 1, "roles": {"customer": {"number": number}}}
        if company:
            contact["company"] = {"name": company}
        else:
            contact["person"] = {"firstName": first, "lastName": last}
        self.contacts[contact_id] = contact
        return contact_id

    def add_voucher(self, number: str, total: str, kind: str = "salesinvoice") -> str:
        """A voucher that is in Lexware Office already."""
        voucher_id = str(uuid.uuid4())
        self.vouchers[voucher_id] = {"type": kind, "voucherNumber": number, "totalGrossAmount": float(total)}
        return voucher_id

    def fail(self, status: int, answer: Any = None, *, times: int = 1) -> None:
        """Answer the next requests with this error."""
        self._forced.extend([(status, answer if answer is not None else {"status": status})] * times)

    def of(self, method: str, path: str = "") -> list[SentRequest]:
        """The requests of a method, whose path begins with ``path``."""
        return [request for request in self.requests if request.method == method and request.path.startswith(path)]

    # --- The server ---

    def __call__(self, method: str, url: str, *, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
        parts = urlsplit(url)
        assert parts.scheme == "https" and parts.netloc == "api.lexware.io", url
        query = {key: values[0] for key, values in parse_qs(parts.query).items()}
        self.requests.append(SentRequest(method, parts.path, query, dict(headers), body))
        if self._forced:
            status, answer = self._forced.pop(0)
            return status, answer if isinstance(answer, bytes) else json.dumps(answer).encode()
        if headers.get("Authorization") != f"Bearer {self.api_key}":
            return 401, json.dumps({"status": 401, "error": "Unauthorized"}).encode()
        status, answer = self._route(method, parts.path, query, headers, body)
        return status, json.dumps(answer).encode()

    def _route(
        self, method: str, path: str, query: dict[str, str], headers: dict[str, str], body: bytes | None
    ) -> tuple[int, Any]:
        if (method, path) == ("GET", "/v1/profile"):
            return 200, {
                "organizationId": "aa93e8a8-2aa3-470b-b914-caad8a255dd8",
                "companyName": self.company,
                "taxType": "net",
                "smallBusiness": False,
            }
        if (method, path) == ("GET", "/v1/posting-categories"):
            return 200, [
                {"id": INCOME, "name": "Einnahmen", "type": "income", "groupName": "Einnahmen"},
                {"id": SERVICE, "name": "Dienstleistung", "type": "income", "groupName": "Einnahmen"},
                {"id": TAX_FREE_EU, "name": "Einnahmen EU", "type": "income", "groupName": "Einnahmen"},
                {"id": "cf03a2b0-f838-474f-ac5e-67adb9b830c7", "name": "Reise MA", "type": "outgo"},
            ]
        if (method, path) == ("GET", "/v1/voucherlist"):
            assert query.get("voucherType") and query.get("voucherStatus"), "both are mandatory"
            found = [
                {
                    "id": voucher_id,
                    "voucherType": voucher["type"],
                    "voucherStatus": "open",
                    "voucherNumber": voucher["voucherNumber"],
                    "totalAmount": voucher["totalGrossAmount"],
                }
                for voucher_id, voucher in self.vouchers.items()
                if voucher["voucherNumber"] == query.get("voucherNumber")
                and voucher["type"] in query["voucherType"].split(",")
            ]
            return 200, {"content": found, "totalElements": len(found), "first": True, "last": True}
        if (method, path) == ("POST", "/v1/vouchers"):
            assert headers.get("Content-Type") == "application/json"
            problems = voucher_problems(json.loads(body or b"{}"), self.contacts)
            if problems:
                return 400, {
                    "status": 400,
                    "error": "Bad Request",
                    "message": "Validation failed",
                    "details": [{"violation": "invalid", "field": name, "message": text} for name, text in problems],
                }
            voucher_id = str(uuid.uuid4())
            self.vouchers[voucher_id] = json.loads(body or b"{}")
            return 200, {"id": voucher_id, "resourceUri": f"https://api.lexware.io/v1/vouchers/{voucher_id}"}
        match = re.fullmatch(r"/v1/vouchers/([0-9a-f-]+)/files", path)
        if method == "POST" and match:
            if match.group(1) not in self.vouchers:
                return 404, {"status": 404, "message": "voucher not found"}
            name, content = parse_upload(headers.get("Content-Type", ""), body or b"")
            self.files.setdefault(match.group(1), []).append((name, content))
            return 202, {"id": str(uuid.uuid4())}
        if (method, path) == ("GET", "/v1/contacts"):
            number = query.get("number")
            found = [
                contact
                for contact in self.contacts.values()
                if str(contact["roles"].get("customer", {}).get("number")) == number
            ]
            return 200, {"content": found, "totalElements": len(found)}
        if (method, path) == ("POST", "/v1/contacts"):
            contact = json.loads(body or b"{}")
            problems = contact_problems(contact)
            if problems:
                return 400, {"IssueList": [{"i18nKey": text, "source": name, "type": "validation_failure"}
                                           for name, text in problems]}  # fmt: skip
            contact_id = str(uuid.uuid4())
            contact = {**contact, "id": contact_id, "version": 1}
            contact["roles"] = {"customer": {"number": self._next_number}}
            self._next_number += 1
            self.contacts[contact_id] = contact
            return 200, {"id": contact_id, "version": 1}
        return 404, {"status": 404, "message": f"unknown: {method} {path}"}


def _two_decimals(value: Any) -> bool:
    return isinstance(value, int | float) and Decimal(str(value)) == Decimal(str(value)).quantize(Decimal("0.01"))


def voucher_problems(voucher: dict[str, Any], contacts: dict[str, Any]) -> list[tuple[str, str]]:
    """What Lexware Office would refuse in a voucher (POST /v1/vouchers, status "open")."""
    problems: list[tuple[str, str]] = []
    for name in sorted(READ_ONLY & set(voucher)):
        problems.append((name, "read-only"))
    if voucher.get("type") not in {"salesinvoice", "salescreditnote", "purchaseinvoice", "purchasecreditnote"}:
        problems.append(("type", "unknown voucher type"))
    if voucher.get("taxType") not in {"net", "gross"}:
        problems.append(("taxType", "must be net or gross"))
    if not isinstance(voucher.get("useCollectiveContact"), bool):
        problems.append(("useCollectiveContact", "required"))
    elif not voucher["useCollectiveContact"] and voucher.get("contactId") not in contacts:
        problems.append(("contactId", "missing_entity"))
    if not voucher.get("voucherNumber"):
        problems.append(("voucherNumber", "required"))
    for name in ("voucherDate", "shippingDate", "dueDate"):
        if name in voucher:
            try:
                datetime.date.fromisoformat(voucher[name])
            except (TypeError, ValueError):
                problems.append((name, "yyyy-MM-dd"))
    if "voucherDate" not in voucher:
        problems.append(("voucherDate", "required"))
    for name in ("totalGrossAmount", "totalTaxAmount"):
        if not _two_decimals(voucher.get(name)):
            problems.append((name, "##.00"))
    items = voucher.get("voucherItems") or []
    if not items:
        problems.append(("voucherItems", "required"))
    gross = tax = Decimal("0")
    for index, item in enumerate(items):
        for name in ("amount", "taxAmount"):
            if not _two_decimals(item.get(name)) or item.get(name, 0) < 0:
                problems.append((f"voucherItems[{index}].{name}", "##.00, not negative"))
        if item.get("taxRatePercent") not in TAX_RATES:
            problems.append((f"voucherItems[{index}].taxRatePercent", "unsupported tax rate"))
        if not re.fullmatch(r"[0-9a-f-]{36}", str(item.get("categoryId", ""))):
            problems.append((f"voucherItems[{index}].categoryId", "required"))
        amount, item_tax = Decimal(str(item.get("amount", 0))), Decimal(str(item.get("taxAmount", 0)))
        gross += amount + item_tax if voucher.get("taxType") == "net" else amount
        tax += item_tax
    if not problems:
        if gross != Decimal(str(voucher["totalGrossAmount"])):
            problems.append(("totalGrossAmount", "must match the sum of all positions"))
        if tax != Decimal(str(voucher["totalTaxAmount"])):
            problems.append(("totalTaxAmount", "must match the sum of all tax amounts"))
    return problems


def contact_problems(contact: dict[str, Any]) -> list[tuple[str, str]]:
    """What Lexware Office would refuse in a new contact (POST /v1/contacts)."""
    problems: list[tuple[str, str]] = []
    if contact.get("version") != 0:
        problems.append(("version", "must be 0"))
    roles = contact.get("roles") or {}
    if not roles or any(role != {} for role in roles.values()):
        problems.append(("roles", "at least one role, each an empty object"))
    if ("company" in contact) == ("person" in contact):
        problems.append(("company", "either company or person"))
    if "company" in contact and not (contact["company"].get("name") or "").strip():
        problems.append(("company.name", "must not be empty"))
    for person in (contact.get("company") or {}).get("contactPersons", []):
        if not person.get("lastName"):
            problems.append(("company.contactPersons.lastName", "must not be empty"))
    if "person" in contact and not (contact["person"].get("lastName") or "").strip():
        problems.append(("person.lastName", "must not be empty"))
    for address in (contact.get("addresses") or {}).get("billing", []):
        if not re.fullmatch(r"[A-Z]{2}", address.get("countryCode", "")):
            problems.append(("addresses.billing.countryCode", "ISO 3166 alpha-2"))
    return problems


def parse_upload(content_type: str, body: bytes) -> tuple[str, bytes]:
    """The file name and content of the field ``file`` of a ``multipart/form-data`` body."""
    match = re.fullmatch(r"multipart/form-data; boundary=(\S+)", content_type)
    assert match, content_type
    boundary = match.group(1).encode()
    parts = [part for part in body.split(b"--" + boundary) if part.strip() not in (b"", b"--")]
    assert len(parts) == 1, "one field"
    head, _separator, content = parts[0].partition(b"\r\n\r\n")
    disposition = re.search(rb'name="file"; filename="([^"]+)"', head)
    assert disposition, head
    assert b"Content-Type: application/pdf" in head
    return disposition.group(1).decode(), content.removesuffix(b"\r\n")
