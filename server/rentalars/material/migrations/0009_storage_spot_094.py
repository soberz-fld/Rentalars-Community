# SPDX-License-Identifier: GPL-3.0-or-later
"""MAT-080: the storage spot of an item inside its storage location."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("material", "0008_dguv_093"),
    ]

    operations = [
        migrations.AddField(
            model_name="materialitem",
            name="storage_spot",
            field=models.CharField(
                blank=True,
                help_text="The place in the storage location, e.g. 01-A-1: shelf or area, bay (letter), height.",
                max_length=12,
                verbose_name="storage spot",
            ),
        ),
    ]
