# SPDX-License-Identifier: GPL-3.0-or-later
"""Base class for tests of the browser pages (UIX).

The tests use the pages the way a person would: open the page, read the form
it shows, change a few fields and send it. :func:`form_data` does the reading:
it collects the values of all fields of a form exactly as a browser would
submit them. A test therefore never has to know every field of a form, only
the ones it wants to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from django.test import Client

from rentalars.accounts.models import User
from tests.helpers import RentalarsTestCase, make_user


@dataclass
class ParsedForm:
    """A form found on a page."""

    action: str
    method: str
    #: Further attributes of the form tag, e.g. ``hx-post``.
    attributes: dict[str, str]
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def target(self) -> str:
        """Where the form is sent to: the htmx address if there is one, else ``action``."""
        return self.attributes.get("hx-post") or self.action


class _FormReader(HTMLParser):
    """Collects the forms of a page with the values a browser would send."""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[ParsedForm] = []
        self._form: ParsedForm | None = None
        self._select: str | None = None
        self._select_multiple = False
        self._select_has_choice = False
        self._first_option: str | None = None
        self._textarea: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if tag == "form":
            self._form = ParsedForm(attributes.get("action", ""), attributes.get("method", "get").lower(), attributes)
            self.forms.append(self._form)
            return
        if self._form is None:
            return
        name = attributes.get("name")
        if tag == "input" and name:
            kind = attributes.get("type", "text")
            if kind in {"checkbox", "radio"}:
                if "checked" in attributes:
                    value = attributes.get("value", "on")
                    if kind == "checkbox" and name in self._form.data:
                        existing = self._form.data[name]
                        self._form.data[name] = [*existing, value] if isinstance(existing, list) else [existing, value]
                    else:
                        self._form.data[name] = value
            elif kind not in {"submit", "button", "file", "image"}:
                self._form.data[name] = attributes.get("value", "")
        elif tag == "select" and name:
            self._select, self._select_multiple = name, "multiple" in attributes
            self._select_has_choice, self._first_option = False, None
            if self._select_multiple:
                self._form.data[name] = []
        elif tag == "option" and self._select:
            value = attributes.get("value", "")
            if self._first_option is None:
                self._first_option = value
            if "selected" in attributes:
                self._select_has_choice = True
                if self._select_multiple:
                    self._form.data[self._select].append(value)
                else:
                    self._form.data[self._select] = value
        elif tag == "textarea" and name:
            self._textarea, self._text = name, []

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._form = None
        elif tag == "select" and self._select and self._form is not None:
            if not self._select_multiple and not self._select_has_choice:
                self._form.data[self._select] = self._first_option or ""
            self._select = None
        elif tag == "textarea" and self._textarea and self._form is not None:
            self._form.data[self._textarea] = "".join(self._text).lstrip("\n")
            self._textarea = None

    def handle_data(self, data: str) -> None:
        if self._textarea:
            self._text.append(data)


def forms_of(response: Any) -> list[ParsedForm]:
    """Return all forms of a page."""
    reader = _FormReader()
    reader.feed(response.content.decode())
    return reader.forms


def form_data(response: Any, containing: str | None = None, **changes: Any) -> dict[str, Any]:
    """Return the data of a form on the page, with some values replaced.

    Args:
        response: The page.
        containing: Pick the form that has a field of this name; without it
            the first form with more than the CSRF field is taken.
        **changes: Field values to set. ``None`` removes a field (an
            unticked checkbox is simply not sent).
    """
    # The quick search of the navigation is on every page (UIX-019); it is never the form a test means first.
    candidates = sorted(forms_of(response), key=lambda form: "nav-search" in form.attributes.get("class", ""))
    if containing is not None:
        candidates = [form for form in candidates if containing in form.data]
    else:
        candidates = [form for form in candidates if set(form.data) - {"csrfmiddlewaretoken"}]
    if not candidates:
        raise AssertionError(f"No form{' with a field ' + containing if containing else ''} on the page.")
    data = dict(candidates[0].data)
    data.pop("csrfmiddlewaretoken", None)
    for name, value in changes.items():
        if value is None:
            data.pop(name, None)
        else:
            data[name] = value
    return data


class UiTestCase(RentalarsTestCase):
    """Provides logged-in browsers for typical users."""

    def setUp(self) -> None:
        super().setUp()
        self.admin_user = make_user("admin", superuser=True)
        self.client.force_login(self.admin_user)

    def browser_for(self, username: str, *roles: str) -> Client:
        """Create a user with the named roles and return a logged-in browser."""
        return self.browser_of(make_user(username, roles=roles))

    def browser_of(self, user: User) -> Client:
        """Return a logged-in browser for an existing user."""
        client = Client()
        client.force_login(user)
        return client

    def htmx(self, method: str, url: str, data: Any = None, client: Client | None = None) -> Any:
        """Send a request the way the planning page does: in the background, expecting a page fragment."""
        send = getattr(client or self.client, method)
        return send(url, data or {}, HTTP_HX_REQUEST="true")

    def messages_of(self, response: Any) -> list[str]:
        """The texts of the messages shown on a page."""
        context = response.context
        if context is None:
            return []
        return [str(message) for message in context["messages"]]

    def assert_ok(self, response: Any) -> str:
        """Check that a page was delivered – without notes meant for developers – and return its text."""
        self.assertEqual(response.status_code, 200, response.content.decode()[:500])
        text = str(response.content.decode())
        for leak in ("{#", "#}", "{%", "%}"):
            self.assertNotIn(leak, text, "template syntax reached the page")
        return text
