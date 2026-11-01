# SPDX-License-Identifier: GPL-3.0-or-later
"""Review: the exchange rate is entered on purpose, positions remember that a person touched them."""

from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def keep_existing_positions(apps, schema_editor):
    """Positions that exist now may have been typed by hand: a new reading must not replace them (R1-5)."""
    apps.get_model("incoming", "InvoicePosition").objects.update(user_edited=True)


def forget_default_rates(apps, schema_editor):
    """An invoice in another currency whose rate is still the old default 1 and that nothing was booked from gets no rate.

    The rate 1 was never entered by anyone; the booking waits for a real one now (R1-4).
    """
    Invoice = apps.get_model("incoming", "IncomingInvoice")
    Item = apps.get_model("material", "MaterialItem")
    booked = set(
        Item.objects.filter(source_position__isnull=False).values_list("source_position__invoice_id", flat=True)
    )
    for invoice in Invoice.objects.exclude(currency__iexact="EUR").filter(exchange_rate=Decimal("1")):
        if invoice.pk not in booked:
            Invoice.objects.filter(pk=invoice.pk).update(exchange_rate=None)


def restore_default_rates(apps, schema_editor):
    """Back to the column that cannot be empty: an empty rate becomes 1 again."""
    apps.get_model("incoming", "IncomingInvoice").objects.filter(exchange_rate__isnull=True).update(
        exchange_rate=Decimal("1")
    )


class Migration(migrations.Migration):
    """Two columns: ``user_edited`` at the positions, a rate that may be empty at the invoices."""

    dependencies = [
        ("incoming", "0001_incoming_invoices_100"),
        ("material", "0010_incoming_invoices_100"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceposition",
            name="user_edited",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.RunPython(keep_existing_positions, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="incominginvoice",
            name="exchange_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                default=None,
                help_text="Euros for one unit of the currency. Needed for an invoice in another currency than the euro: booking in waits for it.",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.000001"))],
                verbose_name="exchange rate",
            ),
        ),
        migrations.RunPython(forget_default_rates, restore_default_rates),
    ]
