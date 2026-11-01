# SPDX-License-Identifier: GPL-3.0-or-later
"""The text line of the planning (PRJ-017)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds ``MaterialLine.is_text``."""

    dependencies = [
        ("projects", "0032_overall_discount_094"),
    ]

    operations = [
        migrations.AddField(
            model_name="materialline",
            name="is_text",
            field=models.BooleanField(
                default=False,
                help_text="A line that only carries a text – a heading or a remark. No product, no quantity, no price.",
                verbose_name="text line",
            ),
        ),
    ]
