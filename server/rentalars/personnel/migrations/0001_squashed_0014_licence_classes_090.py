# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``personnel`` from 0001_initial to 0014_licence_classes_090 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.personnel.models
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('personnel', '0001_initial'), ('personnel', '0002_suggested_job_functions'), ('personnel', '0003_stage5'), ('personnel', '0004_every_person_an_account'), ('personnel', '0005_availability_and_calendars'), ('personnel', '0006_calendar_exchange_state'), ('personnel', '0007_availability_series'), ('personnel', '0008_optional_rates_and_day_rates'), ('personnel', '0009_several_linked_calendars'), ('personnel', '0010_services_071'), ('personnel', '0011_commute_081'), ('personnel', '0012_availability_081'), ('personnel', '0013_profile_084'), ('personnel', '0014_licence_classes_090')]

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('products', '0001_squashed_0008_vehicles_090'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='JobFunction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(error_messages={'unique': 'A job function with this name already exists.'}, max_length=80, unique=True, verbose_name='name')),
                ('guide_cost_rate', models.DecimalField(blank=True, decimal_places=2, help_text='Used in the calculation while a crew line has no person yet.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='guide value for internal costs per hour')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('service_product', models.ForeignKey(help_text='The product whose price the customer pays for this function, per hour.', on_delete=django.db.models.deletion.PROTECT, related_name='job_function', to='products.product', verbose_name='service product')),
                ('max_discount_percent', models.DecimalField(blank=True, decimal_places=2, help_text="No crew line of this function is discounted more – by its own discount, its group's or the project's. 0: never discounted. Empty: no limit.", max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='maximum discount in percent')),
                ('guide_daily_cost_rate', models.DecimalField(blank=True, decimal_places=2, help_text='Used for days while a crew line has no person yet, or the person has no day rate.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='guide value for internal costs per day')),
                ('guide_cost_rate_above_limit', models.DecimalField(blank=True, decimal_places=2, help_text='Internal costs of an hour beyond the limit of hours per day of the service product, while a crew line has no person or the person has no own rate. Empty: the guide value per hour.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='guide value per hour from the limit')),
            ],
            options={
                'verbose_name': 'job function',
                'verbose_name_plural': 'job functions',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(blank=True, max_length=100, verbose_name='first name')),
                ('last_name', models.CharField(max_length=100, verbose_name='last name')),
                ('kind', models.CharField(choices=[('employee', 'permanent employee'), ('temporary', 'temporary staff'), ('freelancer', 'freelancer')], default='employee', max_length=12, verbose_name='kind')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='e-mail')),
                ('phone', models.CharField(blank=True, max_length=60, verbose_name='phone')),
                ('note', models.TextField(blank=True, verbose_name='note')),
                ('company', models.CharField(blank=True, max_length=200, verbose_name='company')),
                ('street', models.CharField(blank=True, max_length=200, verbose_name='street and number')),
                ('postal_code', models.CharField(blank=True, max_length=20, verbose_name='postal code')),
                ('city', models.CharField(blank=True, max_length=120, verbose_name='city')),
                ('tax_number', models.CharField(blank=True, max_length=40, verbose_name='tax number')),
                ('vat_id', models.CharField(blank=True, max_length=40, verbose_name='VAT ID')),
                ('share_phone', models.BooleanField(default=False, help_text='Colleagues on the same deployment. Project management and personnel planning always see it.', verbose_name='colleagues may see my phone number')),
                ('share_email', models.BooleanField(default=False, verbose_name='colleagues may see my e-mail address')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('anonymised_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='anonymised')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('user', models.OneToOneField(editable=False, help_text='The account this person logs in with. Created with the person.', on_delete=django.db.models.deletion.PROTECT, related_name='person', to=settings.AUTH_USER_MODEL, verbose_name='user account')),
                ('position', models.CharField(blank=True, help_text='For example “Head of lighting” – also for the e-mail signature.', max_length=120, verbose_name='position in the company')),
                ('caldav_error', models.CharField(blank=True, editable=False, max_length=250, verbose_name='problem with the CalDAV calendar')),
                ('caldav_password_encrypted', models.TextField(blank=True, editable=False)),
                ('caldav_synced_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='calendar last written')),
                ('caldav_url', models.URLField(blank=True, help_text='The address of a calendar on a CalDAV server, e.g. Nextcloud, iCloud or mailbox.org. Rentalars writes the deployments into it, so that they reach phones even when Rentalars is not reachable from the internet.', max_length=500, verbose_name='CalDAV calendar for my deployments')),
                ('caldav_username', models.CharField(blank=True, max_length=200, verbose_name='CalDAV username')),
                ('calendar_token', models.CharField(blank=True, db_index=True, editable=False, max_length=64)),
                ('caldav_checked_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('caldav_dirty', models.BooleanField(default=False, editable=False)),
                ('caldav_failures', models.PositiveSmallIntegerField(default=0, editable=False)),
                ('commute_km', models.DecimalField(blank=True, decimal_places=1, help_text='Twice this distance (there and back) is deducted once a day per project from trips by kilometre. Empty: nothing is deducted.', max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('2000'))], verbose_name='distance home – company (km)')),
                ('phone_changed_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('email_changed_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('share_phone_changed_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('share_email_changed_at', models.DateTimeField(blank=True, editable=False, null=True)),
            ],
            options={
                'verbose_name': 'person',
                'verbose_name_plural': 'people',
                'ordering': ['last_name', 'first_name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Absence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('vacation', 'holiday'), ('sick', 'sick'), ('unavailable', 'not available')], default='unavailable', max_length=12, verbose_name='kind')),
                ('start', models.DateTimeField(verbose_name='from')),
                ('end', models.DateTimeField(verbose_name='until')),
                ('note', models.CharField(blank=True, max_length=250, verbose_name='note')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='absences', to='personnel.person', verbose_name='person')),
            ],
            options={
                'verbose_name': 'absence',
                'verbose_name_plural': 'absences',
                'ordering': ['start'],
                'indexes': [models.Index(fields=['person', 'start', 'end'], name='absence_person_period_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='PersonJobFunction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hourly_rate', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='hourly rate')),
                ('valid_from', models.DateField(blank=True, null=True, verbose_name='valid from')),
                ('job_function', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='rates', to='personnel.jobfunction', verbose_name='job function')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rates', to='personnel.person', verbose_name='person')),
                ('daily_rate', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='day rate')),
                ('hourly_rate_above_limit', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='hourly rate from the limit')),
            ],
            options={
                'verbose_name': 'job function and rates',
                'verbose_name_plural': 'job functions and rates',
                'ordering': ['job_function__name', models.OrderBy(models.F('valid_from'), descending=True, nulls_last=True)],
                'constraints': [models.UniqueConstraint(fields=('person', 'job_function', 'valid_from'), name='person_rate_unique_per_day')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='QualificationType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('validity_months', models.PositiveSmallIntegerField(blank=True, help_text='Empty: does not expire by itself.', null=True, verbose_name='valid for months')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('licence_classes', models.CharField(blank=True, help_text='Only for a driving licence: the classes it covers, separated by commas, e.g. B, BE.', max_length=60, verbose_name='driving licence classes')),
            ],
            options={
                'verbose_name': 'qualification type',
                'verbose_name_plural': 'qualification types',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Qualification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('detail', models.CharField(blank=True, help_text='e.g. the classes of a driving licence: B, BE, C1E', max_length=200, verbose_name='details')),
                ('acquired_on', models.DateField(blank=True, null=True, verbose_name='acquired on')),
                ('valid_until', models.DateField(blank=True, help_text='Empty: does not expire.', null=True, verbose_name='valid until')),
                ('document', models.FileField(blank=True, max_length=200, upload_to=rentalars.personnel.models.qualification_file_path, verbose_name='certificate')),
                ('document_name', models.CharField(blank=True, max_length=255, verbose_name='file name')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='qualifications', to='personnel.person', verbose_name='person')),
                ('qualification_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='qualifications', to='personnel.qualificationtype', verbose_name='qualification')),
            ],
            options={
                'verbose_name': 'qualification',
                'verbose_name_plural': 'qualifications',
                'ordering': ['qualification_type__name'],
                'constraints': [models.UniqueConstraint(fields=('person', 'qualification_type'), name='qualification_once_per_person')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='AvailabilityMark',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start', models.DateTimeField(verbose_name='from')),
                ('end', models.DateTimeField(verbose_name='until')),
                ('state', models.CharField(choices=[('available', 'available'), ('limited', 'available with limits'), ('unavailable', 'not available')], max_length=12, verbose_name='availability')),
                ('note', models.CharField(blank=True, max_length=250, verbose_name='note')),
                ('source', models.CharField(choices=[('own', 'entered'), ('feed', 'from the linked calendar')], default='own', max_length=8, verbose_name='source')),
                ('feed_uid', models.CharField(blank=True, editable=False, max_length=255)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='availability_marks', to='personnel.person', verbose_name='person')),
                ('entered_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='entered')),
            ],
            options={
                'verbose_name': 'availability',
                'verbose_name_plural': 'availabilities',
                'ordering': ['start'],
            },
        ),
        migrations.CreateModel(
            name='CalendarPush',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uid', models.CharField(max_length=255)),
                ('href', models.CharField(max_length=500)),
                ('etag', models.CharField(blank=True, max_length=255)),
                ('digest', models.CharField(max_length=64)),
                ('pushed_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='calendar_pushes', to='personnel.person')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('person', 'uid'), name='calendar_push_unique_uid')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='AvailabilitySeries',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state', models.CharField(choices=[('available', 'available'), ('limited', 'available with limits'), ('unavailable', 'not available')], max_length=12, verbose_name='availability')),
                ('note', models.CharField(blank=True, max_length=250, verbose_name='note')),
                ('first_day', models.DateField(verbose_name='first day')),
                ('last_day', models.DateField(verbose_name='last day')),
                ('start_time', models.TimeField(blank=True, null=True, verbose_name='from (time)')),
                ('end_time', models.TimeField(blank=True, null=True, verbose_name='until (time)')),
                ('repeat', models.CharField(choices=[('daily', 'daily'), ('weekly', 'weekly'), ('monthly', 'monthly')], max_length=8, verbose_name='repeat')),
                ('interval', models.PositiveSmallIntegerField(default=1, verbose_name='every')),
                ('weekdays', models.CharField(blank=True, max_length=20, verbose_name='weekdays')),
                ('until', models.DateField(blank=True, null=True, verbose_name='until')),
                ('count', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='times')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='availability_series', to='personnel.person', verbose_name='person')),
            ],
            options={
                'verbose_name': 'availability series',
                'verbose_name_plural': 'availability series',
                'ordering': ['first_day', 'pk'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='CalendarFeed',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(max_length=500, verbose_name='address of the calendar (ICS link)')),
                ('label', models.CharField(blank=True, help_text='Only for telling the calendars apart, e.g. “Band”.', max_length=80, verbose_name='name')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('checked_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='last read')),
                ('error', models.CharField(blank=True, editable=False, max_length=250, verbose_name='problem with the calendar')),
                ('failures', models.PositiveSmallIntegerField(default=0, editable=False)),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='calendar_feeds', to='personnel.person', verbose_name='person')),
            ],
            options={
                'verbose_name': 'linked calendar',
                'verbose_name_plural': 'linked calendars',
                'ordering': ['created_at', 'pk'],
                'indexes': [],
                'constraints': [models.UniqueConstraint(fields=('person', 'url'), name='calendar_feed_once_per_person')],
            },
        ),
        migrations.AlterField(
            model_name='jobfunction',
            name='service_product',
            field=models.OneToOneField(help_text='The product whose price the customer pays for this function, per hour.', on_delete=django.db.models.deletion.PROTECT, related_name='job_function', to='products.product', verbose_name='service product'),
        ),
        migrations.AddField(
            model_name='availabilitymark',
            name='series',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marks', to='personnel.availabilityseries', verbose_name='series'),
        ),
        migrations.AddField(
            model_name='availabilitymark',
            name='feed',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='marks', to='personnel.calendarfeed', verbose_name='linked calendar'),
        ),
        migrations.AddIndex(
            model_name='availabilitymark',
            index=models.Index(fields=['person', 'start', 'end'], name='availability_person_period_idx'),
        ),
    ]
