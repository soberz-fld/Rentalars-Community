# SPDX-License-Identifier: GPL-3.0-or-later
"""The number of entries per page, remembered per user and list (UIX-012, page size of every table).

A new empty field of the column choices; nothing to convert. The choice, one cookie per browser for every
list, is not taken over – each list starts with its default again.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add ``TablePreference.page_size``."""

    dependencies = [
        ("core", "0022_approval_reminders_091"),
    ]

    operations = [
        migrations.AddField(
            model_name="tablepreference",
            name="page_size",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="entries per page"),
        ),
    ]
