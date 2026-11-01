# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``documents`` from 0001_initial to 0006_statements_090 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.documents.models
from django.conf import settings
from django.db import migrations, models


#: DOK-005: the texts the templates start with; changed in the administration afterwards.
START_TEMPLATES = {
    "order_confirmation": (
        "Auftragsbestätigung",
        "Vielen Dank für Ihren Auftrag. Wir bestätigen das Projekt {project} „{project_name}“ im Zeitraum {period} "
        "wie folgt:",
        "Wir freuen uns auf die Zusammenarbeit.",
    ),
    "delivery_note": (
        "Lieferschein",
        "Für das Projekt {project} „{project_name}“ liefern wir:",
        "Ware vollständig und unbeschädigt erhalten:",
    ),
    "invoice": (
        "Rechnung",
        "Für das Projekt {project} „{project_name}“ ({period}) berechnen wir:",
        "Bitte überweisen Sie den Betrag bis zum {due_date} unter Angabe der Rechnungsnummer.",
    ),
    "cancellation": ("Stornorechnung", "Hiermit stornieren wir die unten genannte Rechnung vollständig.", ""),
    "crew_sheet": ("Crew-Disposition", "Einsatzplan für das Projekt {project} „{project_name}“, {venue}.", ""),
}


def add_templates(apps, schema_editor):
    """DOK-005: one template per kind of document (documents 0001)."""
    template = apps.get_model("documents", "DocumentTemplate")
    for kind, (title, introduction, closing) in START_TEMPLATES.items():
        template.objects.get_or_create(
            kind=kind, defaults={"title": title, "introduction": introduction, "closing": closing}
        )


#: The texts the template of the offer starts with; changed in the administration afterwards.
OFFER_TEMPLATE = {
    "title": "Angebot",
    "introduction": "Gerne bieten wir Ihnen für das Projekt {project} „{project_name}“ im Zeitraum {period} Folgendes an. "
    "Dieses Angebot gilt bis zum {valid_until}.",
    "closing": "Wir freuen uns auf Ihren Auftrag.",
}


#: The number range of the offers, for installations that exist already (new ones get it from core.defaults).
OFFER_RANGE = {"prefix": "AN-{year}-", "min_digits": 4, "reset_yearly": True}


def add_offer(apps, schema_editor):
    """DOK-010: template and number range of the offer (documents 0002)."""
    apps.get_model("documents", "DocumentTemplate").objects.get_or_create(kind="offer", defaults=OFFER_TEMPLATE)
    apps.get_model("core", "NumberRange").objects.get_or_create(key="offer", defaults=OFFER_RANGE)


#: DOK-010 proposed 14 days; existing installations keep them until somebody changes the template.
OFFER_VALIDITY_DAYS = 14


def offer_validity(apps, schema_editor):
    """DOK-010: the validity of the offer template (documents 0004)."""
    templates = apps.get_model("documents", "DocumentTemplate").objects
    templates.filter(kind="offer", validity_days__isnull=True).update(validity_days=OFFER_VALIDITY_DAYS)



class Migration(migrations.Migration):

    replaces = [('documents', '0001_initial'), ('documents', '0002_offer'), ('documents', '0003_accounting'), ('documents', '0004_offer_options'), ('documents', '0005_labels_084'), ('documents', '0006_statements_090')]

    initial = True

    dependencies = [
        ('core', '0001_squashed_0021_invoice_085'),
        ('customers', '0001_squashed_0007_maps_080'),
        ('projects', '0001_squashed_0003_internal_projects_and_crew_lines'),
        ('timetracking', '0001_squashed_0005_shares_081'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('offer', 'offer'), ('order_confirmation', 'order confirmation'), ('delivery_note', 'delivery note'), ('invoice', 'invoice'), ('cancellation', 'cancellation'), ('crew_sheet', 'crew disposition')], max_length=20, unique=True, verbose_name='kind')),
                ('title', models.CharField(max_length=80, verbose_name='heading')),
                ('introduction', models.TextField(blank=True, verbose_name='introduction')),
                ('closing', models.TextField(blank=True, verbose_name='closing text')),
                ('footer', models.TextField(blank=True, help_text='Printed below address, bank and register details.', verbose_name='additional footer')),
                ('show_logo', models.BooleanField(default=True, verbose_name='print the logo')),
                ('validity_days', models.PositiveSmallIntegerField(blank=True, help_text='How many days a new offer is valid; it can be changed when the offer is made.', null=True, validators=[django.core.validators.MaxValueValidator(3650)], verbose_name='validity in days')),
            ],
            options={
                'verbose_name': 'document template',
                'verbose_name_plural': 'document templates',
                'ordering': ['kind'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='TextBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='name')),
                ('text', models.TextField(verbose_name='text')),
                ('kinds', models.JSONField(blank=True, default=list, help_text='The kinds of documents it is offered for; empty: all.', verbose_name='for')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
            ],
            options={
                'verbose_name': 'text block',
                'verbose_name_plural': 'text blocks',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('offer', 'offer'), ('order_confirmation', 'order confirmation'), ('delivery_note', 'delivery note'), ('invoice', 'invoice'), ('cancellation', 'cancellation'), ('crew_sheet', 'crew disposition')], max_length=20, verbose_name='kind')),
                ('number', models.CharField(max_length=40, unique=True, verbose_name='number')),
                ('title', models.CharField(max_length=120, verbose_name='title')),
                ('issued_on', models.DateField(verbose_name='date')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created')),
                ('content', models.JSONField(default=dict, verbose_name='content')),
                ('net_total', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='net')),
                ('gross_total', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='gross')),
                ('due_on', models.DateField(blank=True, null=True, verbose_name='due on')),
                ('file', models.FileField(max_length=200, upload_to=rentalars.documents.models.document_file_path, verbose_name='PDF')),
                ('sha256', models.CharField(max_length=64, verbose_name='checksum')),
                ('xml_file', models.FileField(blank=True, max_length=200, upload_to=rentalars.documents.models.document_file_path, verbose_name='XRechnung')),
                ('sent_at', models.DateTimeField(blank=True, null=True, verbose_name='sent')),
                ('sent_to', models.CharField(blank=True, max_length=500, verbose_name='sent to')),
                ('cancelled_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='documents.document')),
                ('cancels', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cancellation', to='documents.document')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='documents', to='projects.project', verbose_name='project')),
                ('valid_until', models.DateField(blank=True, null=True, verbose_name='valid until')),
                ('detail', models.CharField(choices=[('lines', 'with positions'), ('groups', 'only groups')], default='lines', max_length=10, verbose_name='level of detail')),
                ('billed_projects', models.ManyToManyField(blank=True, related_name='billed_documents', to='projects.project', verbose_name='projects billed')),
            ],
            options={
                'verbose_name': 'document',
                'verbose_name_plural': 'documents',
                'ordering': ['-created_at', '-id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='AccountingSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lexware_enabled', models.BooleanField(default=False, verbose_name='hand invoices to Lexware Office')),
                ('lexware_api_key_encrypted', models.TextField(blank=True, editable=False)),
                ('lexware_api_key_hint', models.CharField(blank=True, editable=False, max_length=8)),
                ('lexware_automatic', models.BooleanField(default=False, help_text='Every invoice and cancellation goes to Lexware Office as soon as it is made.', verbose_name='hand over at once')),
                ('lexware_collective_contact', models.BooleanField(default=False, help_text='Instead of finding or creating the customer in Lexware Office.', verbose_name='book on the collective contact')),
                ('lexware_categories', models.JSONField(blank=True, default=dict, verbose_name='posting categories')),
                ('lexware_category_choices', models.JSONField(blank=True, default=list, editable=False)),
                ('lexware_organization', models.CharField(blank=True, editable=False, max_length=200)),
                ('lexware_checked_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('datev_consultant_number', models.PositiveIntegerField(blank=True, help_text="The tax adviser's number at DATEV (Beraternummer).", null=True, validators=[django.core.validators.MinValueValidator(1001), django.core.validators.MaxValueValidator(9999999)], verbose_name='consultant number')),
                ('datev_client_number', models.PositiveIntegerField(blank=True, help_text="The company's number at the tax adviser (Mandantennummer).", null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(99999)], verbose_name='client number')),
                ('datev_fiscal_year_start', models.PositiveSmallIntegerField(choices=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9), (10, 10), (11, 11), (12, 12)], default=1, help_text='The month; January when the fiscal year is the calendar year.', verbose_name='fiscal year begins in')),
                ('datev_account_length', models.PositiveSmallIntegerField(default=4, help_text='Number of digits of the general ledger accounts: 4 in most companies. Debtor accounts have one digit more.', validators=[django.core.validators.MinValueValidator(4), django.core.validators.MaxValueValidator(8)], verbose_name='length of general ledger accounts')),
                ('datev_chart', models.CharField(choices=[('SKR03', 'SKR 03'), ('SKR04', 'SKR 04')], default='SKR03', max_length=5, verbose_name='chart of accounts')),
                ('datev_revenue_accounts', models.JSONField(blank=True, default=dict, verbose_name='revenue accounts')),
                ('datev_debitor_mode', models.CharField(choices=[('per_customer', 'one debtor account per customer'), ('collective', 'one collective debtor account')], default='per_customer', max_length=12, verbose_name='debtor accounts')),
                ('datev_debitor_offset', models.PositiveIntegerField(default=0, help_text='Customer 10001 with 0 becomes debtor 10001, with 10000 debtor 20001.', verbose_name='added to the customer number')),
                ('datev_collective_account', models.PositiveIntegerField(blank=True, help_text='e.g. 10000', null=True, verbose_name='collective debtor account')),
            ],
            options={
                'verbose_name': 'accounting settings',
                'verbose_name_plural': 'accounting settings',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='LexwareTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state', models.CharField(choices=[('queued', 'waiting'), ('running', 'running'), ('done', 'handed over'), ('failed', 'failed')], default='queued', max_length=10, verbose_name='state')),
                ('voucher_id', models.CharField(blank=True, max_length=40, verbose_name='voucher in Lexware Office')),
                ('contact_id', models.CharField(blank=True, max_length=40, verbose_name='contact in Lexware Office')),
                ('pdf_uploaded', models.BooleanField(default=False, verbose_name='PDF handed over')),
                ('transferred_at', models.DateTimeField(blank=True, null=True, verbose_name='handed over')),
                ('error', models.TextField(blank=True, verbose_name='error')),
                ('error_code', models.CharField(blank=True, max_length=20)),
                ('attempts', models.PositiveSmallIntegerField(default=0, verbose_name='attempts')),
                ('requested_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='requested')),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('document', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='lexware_transfer', to='documents.document', verbose_name='document')),
                ('job', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='core.backgroundjob')),
                ('requested_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'handing over to Lexware Office',
                'verbose_name_plural': 'handing over to Lexware Office',
                'ordering': ['-requested_at', '-id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='MonthlyStatement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.DateField(verbose_name='month')),
                ('status', models.CharField(choices=[('draft', 'draft'), ('invoiced', 'invoiced'), ('marked', 'marked as invoiced')], default='draft', max_length=10, verbose_name='status')),
                ('content', models.JSONField(blank=True, default=dict, verbose_name='content')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('changed_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='changed')),
                ('marked_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='marked as invoiced')),
                ('cases', models.ManyToManyField(blank=True, related_name='monthly_statements', to='projects.project', verbose_name='service cases')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='monthly_statements', to='customers.customer', verbose_name='customer')),
                ('invoice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='monthly_statements', to='documents.document', verbose_name='invoice')),
                ('marked_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'monthly statement',
                'verbose_name_plural': 'monthly statements',
                'ordering': ['-month', 'customer__name', 'pk'],
                'indexes': [models.Index(fields=['month', 'status'], name='statement_month_status_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='StatementClaim',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('expense', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='statement_claim', to='timetracking.expense', verbose_name='expense')),
                ('statement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='claims', to='documents.monthlystatement', verbose_name='monthly statement')),
                ('time_entry', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='statement_claim', to='timetracking.timeentry', verbose_name='time entry')),
            ],
            options={
                'verbose_name': 'billed time or expense',
                'verbose_name_plural': 'billed times and expenses',
                'indexes': [],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('expense__isnull', True), ('time_entry__isnull', False)), models.Q(('expense__isnull', False), ('time_entry__isnull', True)), _connector='OR'), name='statement_claim_one_thing')],
            },
        ),
        migrations.RunPython(add_templates, migrations.RunPython.noop),
        migrations.RunPython(add_offer, migrations.RunPython.noop),
        migrations.RunPython(offer_validity, migrations.RunPython.noop),
    ]
