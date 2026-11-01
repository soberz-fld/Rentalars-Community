# SPDX-License-Identifier: GPL-3.0-or-later
"""Steuerkonten (tax accounts) for the Eingangsbelege: the model and the start list of SKR 03.

The list is a proposal – accounts a company with event technology often needs – to be checked with the tax adviser;
it is edited under Settings → Master data → Tax accounts. A database that has accounts already (it never has before
this version) is left alone.
"""

from django.db import migrations, models

#: (number, name) – SKR 03.
TAX_ACCOUNTS = [
    ("0027", "EDV-Software"),
    ("0200", "Technische Anlagen und Maschinen"),
    ("0320", "Pkw"),
    ("0350", "Lkw"),
    ("0400", "Betriebsausstattung"),
    ("0410", "Geschäftsausstattung"),
    ("0420", "Büroeinrichtung"),
    ("0480", "Geringwertige Wirtschaftsgüter"),
    ("3100", "Fremdleistungen"),
    ("3200", "Wareneingang"),
    ("3300", "Wareneingang 7 % Vorsteuer"),
    ("3400", "Wareneingang 19 % Vorsteuer"),
    ("3800", "Bezugsnebenkosten"),
    ("3850", "Zölle und Einfuhrabgaben"),
    ("4210", "Miete"),
    ("4240", "Gas, Strom, Wasser"),
    ("4360", "Versicherungen"),
    ("4500", "Fahrzeugkosten"),
    ("4530", "Laufende Kfz-Betriebskosten"),
    ("4540", "Kfz-Reparaturen"),
    ("4600", "Werbekosten"),
    ("4650", "Bewirtungskosten"),
    ("4660", "Reisekosten Arbeitnehmer"),
    ("4670", "Reisekosten Unternehmer"),
    ("4710", "Verpackungsmaterial"),
    ("4730", "Ausgangsfrachten"),
    ("4806", "Wartungskosten für Hard- und Software"),
    ("4809", "Sonstige Reparaturen und Instandhaltungen"),
    ("4810", "Mieten für Einrichtungen (bewegliche Wirtschaftsgüter)"),
    ("4900", "Sonstige betriebliche Aufwendungen"),
    ("4910", "Porto"),
    ("4920", "Telefon"),
    ("4930", "Bürobedarf"),
    ("4950", "Rechts- und Beratungskosten"),
    ("4955", "Buchführungskosten"),
    ("4970", "Nebenkosten des Geldverkehrs"),
    ("4980", "Betriebsbedarf"),
    ("4985", "Werkzeuge und Kleingeräte"),
]


def create_tax_accounts(apps, schema_editor):
    """The start list of SKR 03."""
    TaxAccount = apps.get_model("masterdata", "TaxAccount")
    if TaxAccount.objects.exists():
        return
    for number, name in TAX_ACCOUNTS:
        TaxAccount.objects.create(number=number, name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("masterdata", "0001_squashed_0012_fleet_090"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaxAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "number",
                    models.CharField(
                        error_messages={"unique": "An account with this number exists already."},
                        help_text="As in the chart of accounts of the tax adviser, e.g. 3400.",
                        max_length=10,
                        unique=True,
                        verbose_name="account number",
                    ),
                ),
                ("name", models.CharField(max_length=120, verbose_name="name")),
                ("is_active", models.BooleanField(default=True, verbose_name="active")),
            ],
            options={
                "verbose_name": "tax account",
                "verbose_name_plural": "tax accounts",
                "ordering": ["number"],
            },
        ),
        migrations.RunPython(create_tax_accounts, migrations.RunPython.noop),
    ]
