# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading invoices for "Kauf einpflegen" as a use of AI of its own (purchase entry, MAT-019).

Only new fields, off at first: who reads an uploaded invoice (off, the local AI or a provider), and the new
use in the choices of the call log. No data is changed.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0002_speed_084"),
    ]

    operations = [
        migrations.AddField(
            model_name="aisettings",
            name="invoice_provider",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="ai.aiprovider",
                verbose_name="provider for reading invoices",
            ),
        ),
        migrations.AddField(
            model_name="aisettings",
            name="invoice_source",
            field=models.CharField(
                choices=[
                    ("off", "Off"),
                    ("local", "Local AI"),
                    ("provider", "Provider"),
                ],
                default="off",
                max_length=10,
                verbose_name="reading invoices",
            ),
        ),
        migrations.AlterField(
            model_name="aicall",
            name="use",
            field=models.CharField(
                choices=[
                    ("summary", "Summary of the correspondence"),
                    ("draft", "Reply draft for mails"),
                    ("invoice", "Reading invoices"),
                    ("test", "Test"),
                ],
                max_length=10,
                verbose_name="use",
            ),
        ),
    ]
