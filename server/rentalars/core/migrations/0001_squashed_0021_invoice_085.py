# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``core`` from 0001_initial to 0021_invoice_085 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import datetime
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.core.i18n
import rentalars.core.models
import rentalars.core.uploads
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


#: DOK-005: the number ranges of the documents of stage 5, for installations that exist already.
DOCUMENT_RANGES = {
    "order_confirmation": {"prefix": "AB-{year}-", "min_digits": 4, "reset_yearly": True},
    "delivery_note": {"prefix": "LS-{year}-", "min_digits": 4, "reset_yearly": True},
    "invoice": {"prefix": "RE-{year}-", "min_digits": 4, "reset_yearly": True},
    "crew_sheet": {"prefix": "CD-{year}-", "min_digits": 4, "reset_yearly": True},
}


def add_document_ranges(apps, schema_editor):
    """DOK-005: the number ranges of the documents (core 0004)."""
    number_range = apps.get_model("core", "NumberRange")
    for key, values in DOCUMENT_RANGES.items():
        number_range.objects.get_or_create(key=key, defaults=values)


def create_settings(apps, schema_editor):
    """VFG-036: the one row of the notification settings, with its defaults (core 0020)."""
    NotificationSettings = apps.get_model("core", "NotificationSettings")
    if not NotificationSettings.objects.filter(pk=1).exists():
        NotificationSettings.objects.create(pk=1)


def start_reminders_now(apps, schema_editor):
    """DOK-015: the reminders of invoices count from the installation on (core 0021)."""
    NotificationSettings = apps.get_model("core", "NotificationSettings")
    NotificationSettings.objects.filter(pk=1, invoice_reminders_since__isnull=True).update(
        invoice_reminders_since=timezone.now()
    )



class Migration(migrations.Migration):

    replaces = [('core', '0001_initial'), ('core', '0002_people_see_own_rates'), ('core', '0003_session_upload_settings_and_errors'), ('core', '0004_stage5'), ('core', '0005_offer_number_range'), ('core', '0006_access_log_and_web_backup'), ('core', '0007_noon_to_noon'), ('core', '0008_numbers_063'), ('core', '0009_crew_requests_070'), ('core', '0010_maps_080'), ('core', '0011_surcharges_080'), ('core', '0012_invoices_080'), ('core', '0013_times_080'), ('core', '0014_hints_081'), ('core', '0015_surcharges_081'), ('core', '0016_tables_081'), ('core', '0017_language_083'), ('core', '0018_address_083'), ('core', '0019_ai_083'), ('core', '0020_shortages_084'), ('core', '0021_invoice_085')]

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CompanyProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=200, verbose_name='company name')),
                ('street', models.CharField(blank=True, max_length=200, verbose_name='street and number')),
                ('postal_code', models.CharField(blank=True, max_length=20, verbose_name='postal code')),
                ('city', models.CharField(blank=True, max_length=120, verbose_name='city')),
                ('country', models.CharField(blank=True, default='Deutschland', max_length=80, verbose_name='country')),
                ('phone', models.CharField(blank=True, max_length=60, verbose_name='phone')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='e-mail')),
                ('website', models.CharField(blank=True, max_length=200, verbose_name='website')),
                ('tax_number', models.CharField(blank=True, max_length=60, verbose_name='tax number')),
                ('vat_id', models.CharField(blank=True, max_length=30, verbose_name='VAT identification number')),
                ('bank_name', models.CharField(blank=True, max_length=120, verbose_name='bank')),
                ('iban', models.CharField(blank=True, max_length=42, verbose_name='IBAN')),
                ('bic', models.CharField(blank=True, max_length=11, verbose_name='BIC')),
                ('logo', models.ImageField(blank=True, help_text='PNG or JPEG, at most 2 MB.', upload_to='company/', validators=[rentalars.core.uploads.validate_image_upload], verbose_name='logo')),
                ('payment_terms_days', models.PositiveSmallIntegerField(default=14, help_text='For invoices, unless the customer has terms of its own.', verbose_name='payment terms in days')),
                ('register_details', models.CharField(blank=True, help_text='Printed in the footer of documents, e.g. “Amtsgericht Musterstadt HRB 1234 · Managing director: …”', max_length=250, verbose_name='register and management')),
                ('warehouse_address', models.CharField(blank=True, help_text='Where the trips of the projects start and end, in one line, e.g. “5 Harbour Road, 12345 Sampletown”. Empty: the address of the company.', max_length=250, verbose_name='address of the warehouse')),
                ('document_language', models.CharField(choices=[('de', 'Deutsch'), ('en', 'English')], default=rentalars.core.i18n.installation_language, help_text='Offers, order confirmations, delivery notes, invoices and packing lists, and the mails Rentalars writes to customers by itself. Only the fixed texts follow this language: what you typed yourself – document templates, text blocks, mail templates, product names – stays as you wrote it.', max_length=5, verbose_name='language of documents')),
            ],
            options={
                'verbose_name': 'company profile',
                'verbose_name_plural': 'company profile',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='NumberRange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(choices=[('project', 'Projects'), ('customer', 'Customers'), ('material_item', 'Material IDs'), ('document', 'Documents'), ('offer', 'Offers'), ('order_confirmation', 'Order confirmations'), ('delivery_note', 'Delivery notes'), ('invoice', 'Invoices and cancellations'), ('crew_sheet', 'Crew dispositions')], max_length=30, unique=True, verbose_name='range')),
                ('prefix', models.CharField(blank=True, help_text='Text in front of the number. {year} is replaced by the current year.', max_length=30, verbose_name='prefix')),
                ('min_digits', models.PositiveSmallIntegerField(default=4, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)], verbose_name='minimum number of digits')),
                ('start_value', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)], verbose_name='start value')),
                ('next_value', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)], verbose_name='next number')),
                ('reset_yearly', models.BooleanField(default=False, verbose_name='restart every year')),
                ('current_year', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='year of the counter')),
            ],
            options={
                'verbose_name': 'number range',
                'verbose_name_plural': 'number ranges',
                'ordering': ['key'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='SystemSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('setup_completed', models.BooleanField(default=False, verbose_name='first-run setup completed')),
                ('defaults_installed', models.BooleanField(default=False, verbose_name='start data installed')),
                ('setup_token', models.CharField(blank=True, help_text='Protects the first-run setup on a server; empty in development.', max_length=64, verbose_name='setup token')),
                ('buffer_before_hours', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=6, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='buffer before use (hours)')),
                ('buffer_after_hours', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=6, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='buffer after use (hours)')),
                ('default_start_time', models.TimeField(default=datetime.time(12, 0), verbose_name='usual start time')),
                ('default_end_time', models.TimeField(default=datetime.time(12, 0), help_text='Not after the start time: the project ends on the following day.', verbose_name='usual end time')),
                ('password_min_length', models.PositiveSmallIntegerField(default=10, validators=[django.core.validators.MinValueValidator(8), django.core.validators.MaxValueValidator(128)], verbose_name='minimum password length')),
                ('login_max_attempts', models.PositiveSmallIntegerField(default=5, validators=[django.core.validators.MinValueValidator(3), django.core.validators.MaxValueValidator(50)], verbose_name='failed logins before lockout')),
                ('login_lockout_minutes', models.PositiveSmallIntegerField(default=15, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(1440)], verbose_name='lockout duration (minutes)')),
                ('people_see_own_rates', models.BooleanField(default=True, help_text='Applies to accounts without the right to see personnel costs: in their own times and deployments.', verbose_name='people may see their own hourly rates')),
                ('mail_tag_prefix', models.CharField(default='RL', help_text='The tag reads [RL#2026-0042] with the prefix RL. Changing it, answers to older mails still need the old one.', max_length=10, validators=[django.core.validators.RegexValidator('^[A-Za-z0-9]+$', 'Letters and digits only.')], verbose_name='prefix of the project tag in mails')),
                ('max_upload_mb', models.PositiveSmallIntegerField(default=50, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(500)], verbose_name='largest file to upload (MB)')),
                ('session_idle_minutes', models.PositiveIntegerField(default=240, validators=[django.core.validators.MinValueValidator(5), django.core.validators.MaxValueValidator(10080)], verbose_name='log out after … minutes without activity')),
                ('two_factor_for_administrators', models.BooleanField(default=False, help_text='Everybody who may change the settings, and every account with all rights.', verbose_name='two-factor login required for administrators')),
                ('api_requests_per_minute', models.PositiveIntegerField(default=600, help_text='More calls are answered with “too many requests” until the minute is over. 0: no limit.', validators=[django.core.validators.MaxValueValidator(100000)], verbose_name='API calls per token and minute')),
                ('retention_change_log_days', models.PositiveIntegerField(default=0, help_text='Who changed what and when. 0: for good.', validators=[django.core.validators.MaxValueValidator(36500)], verbose_name='keep the change log (days)')),
                ('retention_jobs_days', models.PositiveIntegerField(default=7, help_text='Imports, labels, full exports – with their files.', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(365)], verbose_name='keep results of background tasks (days)')),
                ('retention_notifications_days', models.PositiveIntegerField(default=180, validators=[django.core.validators.MinValueValidator(7), django.core.validators.MaxValueValidator(3650)], verbose_name='keep notifications (days)')),
                ('retention_security_log_days', models.PositiveIntegerField(default=365, help_text='Logins, failed logins, changes to users and roles.', validators=[django.core.validators.MinValueValidator(30), django.core.validators.MaxValueValidator(3650)], verbose_name='keep the security log (days)')),
                ('retention_access_log_days', models.PositiveIntegerField(default=180, help_text='Who opened or downloaded customers, people, projects, exports and backups.', validators=[django.core.validators.MinValueValidator(30), django.core.validators.MaxValueValidator(3650)], verbose_name='keep the access log (days)')),
                ('ask_again_on_new_times', models.BooleanField(default=True, help_text='When the times of a crew line that was asked for or accepted change, the person gets a new request and the line shows “asked” again until the answer comes. Not for declined lines.', verbose_name='ask again when the times change')),
                ('maps_load_at_once', models.BooleanField(default=False, help_text='Off: a map appears after a click on “Show map”; only then is the address sent to OpenStreetMap and the map loaded. On: every page with an address shows its map right away.', verbose_name='load maps at once')),
                ('invoices_enabled', models.BooleanField(default=True, help_text='Off: no invoice and no cancellation can be made, and handing them to Lexware Office and the DATEV export are hidden. Invoices made before stay readable with their projects; projects are closed without an invoice.', verbose_name='make invoices in Rentalars')),
                ('time_hint_day_hours', models.DecimalField(decimal_places=1, default=Decimal('10'), help_text='The hours of work of one person on one working day, breaks not counted. 0: no hint.', max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='hint: working day longer than … hours')),
                ('time_hint_break_hours', models.DecimalField(decimal_places=1, default=Decimal('6'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='hint: a break is due after more than … hours of work')),
                ('time_hint_break_minutes', models.PositiveSmallIntegerField(default=30, help_text='The recorded breaks and the gaps between the entries of the day count. 0: no hint.', validators=[django.core.validators.MaxValueValidator(600)], verbose_name='hint: that break lasts at least … minutes')),
                ('time_hint_long_break_hours', models.DecimalField(decimal_places=1, default=Decimal('9'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='hint: a longer break is due after more than … hours of work')),
                ('time_hint_long_break_minutes', models.PositiveSmallIntegerField(default=45, validators=[django.core.validators.MaxValueValidator(600)], verbose_name='hint: the longer break lasts at least … minutes')),
                ('time_hint_rest_hours', models.DecimalField(decimal_places=1, default=Decimal('11'), help_text='0: no hint.', max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='hint: rest between two working days shorter than … hours')),
                ('expense_km_rate', models.DecimalField(decimal_places=2, default=Decimal('0.30'), help_text='For trips with the own car entered as expenses. A trip keeps the rate it was recorded with.', max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('10'))], verbose_name='travel costs per kilometre')),
                ('time_hints_enabled', models.BooleanField(default=True, help_text='Long working day, short break, short rest – where times are entered, in the approval, the report and the API. Off: no hints anywhere; the limits below are kept.', verbose_name='show hints at working times')),
                ('expense_deduct_commute', models.BooleanField(default=True, help_text='Twice the distance home – company of the person is deducted once a day per project from trips by kilometre. Trips recorded before keep their amount.', verbose_name='deduct the way to work from trips')),
            ],
            options={
                'verbose_name': 'system settings',
                'verbose_name_plural': 'system settings',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='AuditLogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='time')),
                ('actor_label', models.CharField(blank=True, max_length=150, verbose_name='user name')),
                ('action', models.CharField(choices=[('created', 'created'), ('updated', 'changed'), ('deleted', 'deleted'), ('event', 'event')], max_length=10, verbose_name='action')),
                ('event', models.CharField(blank=True, max_length=60, verbose_name='event')),
                ('object_id', models.CharField(max_length=40)),
                ('object_repr', models.CharField(max_length=200, verbose_name='object')),
                ('changes', models.JSONField(blank=True, default=dict, verbose_name='changes')),
                ('parent_object_id', models.CharField(blank=True, max_length=40)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='user')),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contenttypes.contenttype')),
                ('parent_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contenttypes.contenttype')),
            ],
            options={
                'verbose_name': 'change log entry',
                'verbose_name_plural': 'change log',
                'ordering': ['-timestamp', '-id'],
                'indexes': [models.Index(fields=['content_type', 'object_id'], name='audit_object_idx'), models.Index(fields=['parent_content_type', 'parent_object_id'], name='audit_parent_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='ErrorRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('signature', models.CharField(max_length=64, unique=True)),
                ('source', models.CharField(max_length=200, verbose_name='where')),
                ('message', models.TextField(verbose_name='error')),
                ('details', models.TextField(blank=True, verbose_name='details')),
                ('count', models.PositiveIntegerField(default=1, verbose_name='how often')),
                ('first_seen', models.DateTimeField(default=django.utils.timezone.now, verbose_name='first')),
                ('last_seen', models.DateTimeField(default=django.utils.timezone.now, verbose_name='last')),
                ('reported_at', models.DateTimeField(blank=True, null=True, verbose_name='reported')),
            ],
            options={
                'verbose_name': 'error',
                'verbose_name_plural': 'errors',
                'ordering': ['-last_seen'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='BackgroundJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(max_length=30, verbose_name='kind')),
                ('title', models.CharField(max_length=200, verbose_name='task')),
                ('params', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('queued', 'waiting'), ('running', 'running'), ('done', 'ready'), ('failed', 'failed')], default='queued', max_length=10, verbose_name='status')),
                ('progress', models.PositiveSmallIntegerField(default=0, verbose_name='progress')),
                ('message', models.TextField(blank=True, verbose_name='message')),
                ('result_file', models.FileField(blank=True, max_length=200, upload_to=rentalars.core.models.job_file_path)),
                ('result_name', models.CharField(blank=True, max_length=200)),
                ('result', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='started')),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='finished')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='background_jobs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'background task',
                'verbose_name_plural': 'background tasks',
                'ordering': ['-created_at', '-id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='TablePreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('table', models.CharField(max_length=60, verbose_name='list')),
                ('columns', models.JSONField(default=list, verbose_name='columns')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='changed')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='table_preferences', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'column choice',
                'verbose_name_plural': 'column choices',
                'constraints': [models.UniqueConstraint(fields=('user', 'table'), name='table_preference_unique')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='AccessLogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='time')),
                ('user_label', models.CharField(blank=True, max_length=150, verbose_name='user name')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP address')),
                ('action', models.CharField(choices=[('view', 'opened'), ('download', 'downloaded'), ('export', 'exported'), ('api', 'read through the API')], max_length=10, verbose_name='access')),
                ('object_type', models.CharField(choices=[('customer', 'customer'), ('person', 'person'), ('project', 'project'), ('mail', 'project mail'), ('attachment', 'mail attachment'), ('project_file', 'project file'), ('document', 'document'), ('list', 'list'), ('full_export', 'full export'), ('backup', 'backup')], max_length=20, verbose_name='kind of object')),
                ('object_id', models.CharField(blank=True, max_length=60, verbose_name='object ID')),
                ('label', models.CharField(blank=True, max_length=200, verbose_name='object')),
                ('parent_type', models.CharField(blank=True, choices=[('customer', 'customer'), ('person', 'person'), ('project', 'project'), ('mail', 'project mail'), ('attachment', 'mail attachment'), ('project_file', 'project file'), ('document', 'document'), ('list', 'list'), ('full_export', 'full export'), ('backup', 'backup')], max_length=20)),
                ('parent_id', models.CharField(blank=True, max_length=40)),
                ('path', models.CharField(blank=True, max_length=300, verbose_name='page address')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'access log entry',
                'verbose_name_plural': 'access log',
                'ordering': ['-timestamp', '-id'],
                'indexes': [models.Index(fields=['object_type', 'object_id'], name='access_object_idx'), models.Index(fields=['parent_type', 'parent_id'], name='access_parent_idx'), models.Index(fields=['user', 'timestamp'], name='access_user_time_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='AddressPosition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=64, unique=True)),
                ('address', models.CharField(max_length=500, verbose_name='address')),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='latitude')),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='longitude')),
                ('source', models.CharField(choices=[('found', 'found by OpenStreetMap'), ('not_found', 'not found'), ('manual', 'set by hand')], max_length=10, verbose_name='source')),
                ('found_name', models.CharField(blank=True, max_length=300, verbose_name='found as')),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='changed')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='changed by')),
            ],
            options={
                'verbose_name': 'position of an address',
                'verbose_name_plural': 'positions of addresses',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='TimeSurchargeSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('on_price', models.BooleanField(default=False, help_text='Crew lines planned from now on get them, if billed by the hour; each line can be changed. Lines planned before stay as they are.', verbose_name='surcharges on the price for the customer')),
                ('on_costs', models.BooleanField(default=False, help_text='Crew lines planned from now on get them, if billed by the hour; each line can be changed. Lines planned before stay as they are.', verbose_name='surcharges on the personnel costs')),
                ('state', models.CharField(blank=True, choices=[('', 'only the holidays of the whole country'), ('BW', 'Baden-Württemberg'), ('BY', 'Bavaria (with Assumption Day, as in most communities)'), ('BYE', 'Bavaria without Assumption Day'), ('BYA', 'Bavaria, city of Augsburg (with the Peace Festival)'), ('BE', 'Berlin'), ('BB', 'Brandenburg'), ('HB', 'Bremen'), ('HH', 'Hamburg'), ('HE', 'Hesse'), ('MV', 'Mecklenburg-Western Pomerania'), ('NI', 'Lower Saxony'), ('NW', 'North Rhine-Westphalia'), ('RP', 'Rhineland-Palatinate'), ('SL', 'Saarland'), ('SN', 'Saxony'), ('SNF', 'Saxony, communities with Corpus Christi'), ('ST', 'Saxony-Anhalt'), ('SH', 'Schleswig-Holstein'), ('TH', 'Thuringia'), ('THF', 'Thuringia, communities with Corpus Christi')], default='', help_text='The holidays of the federal state where the work is done; the same for every project.', max_length=3, verbose_name='public holidays of')),
                ('german_holidays', models.BooleanField(default=True, help_text='Off: only the own holidays count – for work in another country.', verbose_name='statutory holidays of Germany')),
                ('next_day_until', models.TimeField(blank=True, default=datetime.time(4, 0), help_text='Sundays, holidays and other days of the rules count until this time of the next day if the work began before midnight – § 3b EStG: 4:00. Empty: they end at midnight.', null=True, verbose_name='for work begun before midnight, a day with a surcharge reaches into the next day until')),
                ('rules_set_up', models.BooleanField(default=False, editable=False)),
            ],
            options={
                'verbose_name': 'surcharges for night, Sunday and holidays',
                'verbose_name_plural': 'surcharges for night, Sunday and holidays',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='OwnHoliday',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, verbose_name='name')),
                ('kind', models.CharField(choices=[('yearly', 'every year on'), ('once', 'once on'), ('easter', 'days from Easter Sunday')], default='yearly', max_length=10, verbose_name='when')),
                ('day', models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)], verbose_name='day')),
                ('month', models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)], verbose_name='month')),
                ('date', models.DateField(blank=True, null=True, verbose_name='date')),
                ('easter_offset', models.SmallIntegerField(blank=True, help_text='Easter Monday 1, Ascension 39, Whit Monday 50, Corpus Christi 60; before Easter negative.', null=True, validators=[django.core.validators.MinValueValidator(-80), django.core.validators.MaxValueValidator(240)], verbose_name='days from Easter Sunday')),
            ],
            options={
                'verbose_name': 'own holiday',
                'verbose_name_plural': 'own holidays',
                'ordering': ['id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='TimeSurchargeRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('name', models.CharField(help_text='Shown in the planning and in documents; rules with the same name and rate count as one.', max_length=80, verbose_name='name')),
                ('kind', models.CharField(choices=[('time', 'at a time of day'), ('weekday', 'on weekdays'), ('holiday', 'on public holidays'), ('date', 'on a day of the year')], default='time', max_length=10, verbose_name='applies')),
                ('time_from', models.TimeField(blank=True, null=True, verbose_name='from')),
                ('time_until', models.TimeField(blank=True, null=True, verbose_name='until')),
                ('weekdays', models.CharField(blank=True, default='', max_length=7, verbose_name='weekdays')),
                ('day', models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)], verbose_name='day')),
                ('month', models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)], verbose_name='month')),
                ('begun_before_midnight', models.BooleanField(default=False, help_text='Then it takes the place of the other time-of-day rules, as the 40 percent from 0:00 to 4:00.', verbose_name='only for work begun before midnight')),
                ('price_percent', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('500'))], verbose_name='on the price, in percent')),
                ('cost_percent', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('500'))], verbose_name='on the costs, in percent')),
                ('code', models.CharField(blank=True, default='', editable=False, max_length=30)),
            ],
            options={
                'verbose_name': 'surcharge rule',
                'verbose_name_plural': 'surcharge rules',
                'ordering': ['position', 'id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='AddressChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(editable=False, max_length=32, unique=True)),
                ('host', models.CharField(max_length=253, verbose_name='host name')),
                ('certificate_kind', models.CharField(choices=[('letsencrypt', "Let's Encrypt"), ('selfsigned', 'Self-signed certificate'), ('own', 'Own certificate'), ('proxy', 'A server in front encrypts')], max_length=20, verbose_name='certificate')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name="e-mail address for Let's Encrypt")),
                ('redirect_old', models.BooleanField(default=True, verbose_name='redirect the old address')),
                ('previous_url', models.CharField(blank=True, max_length=300, verbose_name='previous address')),
                ('certificate_info', models.JSONField(blank=True, default=dict)),
                ('checks', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(choices=[('prepared', 'prepared'), ('applied', 'applied'), ('failed', 'failed'), ('superseded', 'replaced by a newer one'), ('discarded', 'discarded')], default='prepared', max_length=20, verbose_name='status')),
                ('prepared_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='prepared')),
                ('applied_at', models.DateTimeField(blank=True, null=True, verbose_name='applied')),
                ('applied_by', models.CharField(blank=True, max_length=100, verbose_name='applied by')),
                ('result_message', models.TextField(blank=True, verbose_name='result')),
                ('result', models.JSONField(blank=True, default=dict)),
                ('prepared_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='prepared by')),
            ],
            options={
                'verbose_name': 'change of the server address',
                'verbose_name_plural': 'changes of the server address',
                'ordering': ['-prepared_at', '-id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='NotificationSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('shortage_interval', models.CharField(choices=[('daily', 'Every day'), ('workdays', 'On working days (Monday to Friday, except holidays)'), ('weekly', 'Once a week'), ('off', 'Never – switched off')], default='daily', help_text='“On working days” leaves out the holidays set under Settings → Surcharges.', max_length=10, verbose_name='how often')),
                ('shortage_weekday', models.PositiveSmallIntegerField(choices=[(1, 'Monday'), (2, 'Tuesday'), (3, 'Wednesday'), (4, 'Thursday'), (5, 'Friday'), (6, 'Saturday'), (7, 'Sunday')], default=1, help_text='For “Once a week”.', verbose_name='day of the week')),
                ('shortage_time', models.TimeField(default=datetime.time(4, 15), help_text='Rentalars checks within a minute of this time and reports what it finds.', verbose_name='time of day')),
                ('shortage_lead_weeks', models.PositiveSmallIntegerField(default=4, help_text='Shortages of projects that begin within this many weeks – 1 to 26.', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(26)], verbose_name='how far ahead (weeks)')),
                ('shortage_repeat', models.BooleanField(default=False, help_text='Off: each shortage is reported once – again only if it grows, or if it was resolved and comes back. On: every check reports all open shortages again, as a reminder.', verbose_name='report known shortages again at every check')),
                ('shortage_last_run', models.DateTimeField(blank=True, editable=False, null=True)),
                ('shortage_checked_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='last check')),
                ('shortage_reported', models.PositiveIntegerField(default=0, editable=False, verbose_name='reported at the last check')),
                ('invoice_checked_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='last check')),
                ('invoice_every_days', models.PositiveSmallIntegerField(default=7, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(60)], verbose_name='then again every (days)')),
                ('invoice_first_days', models.PositiveSmallIntegerField(default=1, help_text='Days after the day the project was closed; 0: at the next check after closing.', validators=[django.core.validators.MaxValueValidator(60)], verbose_name='first reminder after (days)')),
                ('invoice_last_run', models.DateTimeField(blank=True, editable=False, null=True)),
                ('invoice_reminded', models.PositiveIntegerField(default=0, editable=False, verbose_name='reminded at the last check')),
                ('invoice_reminders', models.BooleanField(default=True, help_text='Closed projects without invoice are reminded of until the invoice is made – or, with invoices written in another program, until “Invoice issued” is ticked.', verbose_name='remind of invoices')),
                ('invoice_reminders_since', models.DateTimeField(blank=True, editable=False, null=True)),
                ('invoice_service_cases', models.BooleanField(default=False, help_text='Done service cases with something to charge are reminded of as well.', verbose_name='service cases too')),
                ('invoice_time', models.TimeField(default=datetime.time(9, 0), verbose_name='time of day')),
                ('invoice_user', models.ForeignKey(blank=True, help_text='Besides the project manager – and for projects without one. Empty: only the project manager.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='also remind')),
            ],
            options={
                'verbose_name': 'notification settings of the company',
                'verbose_name_plural': 'notification settings of the company',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.RunPython(add_document_ranges, migrations.RunPython.noop),
        migrations.RunPython(create_settings, migrations.RunPython.noop),
        migrations.RunPython(start_reminders_now, migrations.RunPython.noop),
    ]
