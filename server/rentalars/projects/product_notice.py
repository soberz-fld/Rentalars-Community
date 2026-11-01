# SPDX-License-Identifier: GPL-3.0-or-later
"""Tell the people of a project that a product planned in it was changed (PRJ-072).

Whoever changes a product - in the form, through the API or by an import - saves it; the signal ``post_save`` of
the product then looks, once the change is committed, for lines of that product in projects that are not
fully confirmed yet (inquiry, option, "Confirmed – details open") which have not taken the change over. The project manager and the members who may
edit the project get one notification per project ("Product changed in a project not yet fully confirmed"). Nothing is
sent again while an earlier notification of the same project is still unread, so that a series of changes (or an
import of a thousand products) does not flood anybody. The notification names no prices; the planning shows them
to who has the price right.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy, ngettext_lazy

from rentalars.core.i18n import LocalText

logger = logging.getLogger(__name__)


#: The fields of a product that lines follow (see ``projects.product_changes``). Saving a product without a change
#: in one of them (deactivating it, a note, the category) tells nobody.
FOLLOWED_FIELDS = (
    "name",
    "unit_id",
    "tax_rate_id",
    "billing_mode",
    "price",
    "sale_price",
    "surcharge_percent",
    "hours_limit",
    "price_above_limit",
)

#: Nobody is told again about the same project within this time, read or not (a user who only wants e-mails has
#: every notification marked as read at once; an import of many products must not send a mail for each).
QUIET_TIME = datetime.timedelta(hours=1)


def connect() -> None:
    """Connect the signals; called from ``ProjectsConfig.ready``."""
    from django.db.models.signals import post_save, pre_save

    pre_save.connect(product_saving, sender="products.Product", dispatch_uid="projects.product_notice.before")
    post_save.connect(product_saved, sender="products.Product", dispatch_uid="projects.product_notice")


def product_saving(sender: Any, instance: Any, raw: bool = False, **kwargs: Any) -> None:
    """Before a product is saved: note whether a field that lines follow is about to change."""
    instance._followed_changed = False
    if raw or instance.pk is None:
        return
    stored = type(instance).objects.filter(pk=instance.pk).values(*FOLLOWED_FIELDS).first()
    if stored is not None:
        instance._followed_changed = any(getattr(instance, name) != value for name, value in stored.items())


def product_saved(sender: Any, instance: Any, created: bool = False, raw: bool = False, **kwargs: Any) -> None:
    """After a product was changed: tell the projects once the change is committed."""
    if created or raw or not getattr(instance, "_followed_changed", False):
        return
    product_id = instance.pk
    transaction.on_commit(lambda: _tell_safely(product_id))


def _tell_safely(product_id: int) -> None:
    """Tell the projects; a failure is logged and never reaches the person who saved the product."""
    try:
        tell_projects_about(product_id)
    except Exception:
        logger.exception("Telling the projects about product %s failed", product_id)


def tell_projects_about(product_id: int) -> int:
    """Notify the people of every not yet confirmed project whose lines differ from the product.

    Whoever has the price right is told about price changes too; the others only about what they can see in the
    planning (a notification must not be the way to learn that a price changed).

    Args:
        product_id: The product that was saved.

    Returns:
        How many projects were told.
    """
    from rentalars.accounts.rights import SpecialRight
    from rentalars.notifications.models import Kind, Notification
    from rentalars.notifications.services import notify, project_people
    from rentalars.products.models import Product
    from rentalars.projects.product_changes import changes_of_product

    product = Product.objects.filter(pk=product_id).select_related("unit", "tax_rate").first()
    if product is None:
        return 0
    with_prices = changes_of_product(product, with_prices=True)
    without_prices = changes_of_product(product, with_prices=False)
    told = 0
    for project, changes in with_prices.items():
        people = [user for user in project_people(project) if user is not None]
        recent = timezone.now() - QUIET_TIME
        quiet = set(
            Notification.objects.filter(kind=Kind.PRODUCT_CHANGE, project=project)
            .filter(Q(read_at__isnull=True) | Q(created_at__gte=recent))
            .values_list("user_id", flat=True)
        )
        people = [user for user in people if user.pk not in quiet]
        plain = len(without_prices.get(project, []))
        groups = [
            ([user for user in people if user.rights.has(SpecialRight.PRICES)], len(changes)),
            ([user for user in people if not user.rights.has(SpecialRight.PRICES)], plain),
        ]
        was_told = False
        for recipients, count in groups:
            if not recipients or not count:
                continue
            was_told = True
            notify(
                recipients,
                Kind.PRODUCT_CHANGE,
                LocalText(gettext_lazy("%(project)s: %(product)s was changed"), project=project, product=product.name),
                body=LocalText(
                    ngettext_lazy(
                        "%(count)d line of the project differs from the product. Check it in the planning and "
                        "take the change over.",
                        "%(count)d lines of the project differ from the product. Check them in the planning and "
                        "take the changes over.",
                        "count",
                    ),
                    count=count,
                ),
                url=reverse("projects:detail", args=[project.pk]) + "#product-changes",
                project=project,
            )
        told += was_told
    return told
