# SPDX-License-Identifier: GPL-3.0-or-later
"""Review: the pieces a row was booked in with stay known when bulk material is built in or sold (R1-2)."""

from django.db import migrations, models


def fill_source_quantity(apps, schema_editor):
    """Rows made from an invoice position: the quantity they have now plus what was built in or sold since."""
    Item = apps.get_model("material", "MaterialItem")
    Installed = apps.get_model("material", "InstalledQuantity")
    Sale = apps.get_model("material", "SaleFromStock")
    for item in Item.objects.filter(source_position__isnull=False, source_quantity__isnull=True).select_related(
        "material_model"
    ):
        if item.material_model.tracking_mode != "bulk":
            pieces = 1
        else:
            built_in = sum(Installed.objects.filter(material=item).values_list("quantity", flat=True))
            sold = sum(
                Sale.objects.filter(item=item, cancelled_at__isnull=True, item_left=False).values_list(
                    "quantity", flat=True
                )
            )
            pieces = item.quantity + built_in + sold
        Item.objects.filter(pk=item.pk).update(source_quantity=pieces)


class Migration(migrations.Migration):
    """One column; the rows booked in so far get their number."""

    dependencies = [
        ("material", "0013_depreciation_sales_100"),
    ]

    operations = [
        migrations.AddField(
            model_name="materialitem",
            name="source_quantity",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(fill_source_quantity, migrations.RunPython.noop),
    ]
