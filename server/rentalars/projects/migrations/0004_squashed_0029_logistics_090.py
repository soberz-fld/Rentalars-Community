# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``projects`` from 0004_phases_files_open_items_requests to 0029_logistics_090 in one.

Squashed: a new database is built from here, and a database that has applied the replaced
migrations counts it as applied (``replaces``). Data steps that only converted the data of older
versions are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.projects.models
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('projects', '0004_phases_files_open_items_requests'), ('projects', '0005_stage5'), ('projects', '0006_lines_051'), ('projects', '0007_templates_and_cleaning'), ('projects', '0008_subprojects'), ('projects', '0009_crew_phases_and_days'), ('projects', '0010_lines_062'), ('projects', '0011_phases_063'), ('projects', '0012_numbers_063'), ('projects', '0013_dry_hire_template_063'), ('projects', '0014_numbers_070'), ('projects', '0015_crew_requests_070'), ('projects', '0016_crew_071'), ('projects', '0017_subrentals_071'), ('projects', '0018_follow_up_071'), ('projects', '0019_service_cases_080'), ('projects', '0020_trips_080'), ('projects', '0021_surcharges_080'), ('projects', '0022_followups_081'), ('projects', '0023_participants_081'), ('projects', '0024_trips_082'), ('projects', '0025_case_status_083'), ('projects', '0026_field_changes_084'), ('projects', '0027_invoice_085'), ('projects', '0028_defects_085'), ('projects', '0029_logistics_090')]

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('customers', '0001_squashed_0007_maps_080'),
        ('mail', '0001_squashed_0013_senders_signatures_inquiries_090'),
        ('masterdata', '0001_squashed_0012_fleet_090'),
        ('material', '0001_squashed_0006_vehicles_090'),
        ('personnel', '0001_squashed_0014_licence_classes_090'),
        ('products', '0001_squashed_0008_vehicles_090'),
        ('projects', '0001_squashed_0003_internal_projects_and_crew_lines'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OpenItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(max_length=250, verbose_name='open item')),
                ('is_done', models.BooleanField(default=False, verbose_name='done')),
                ('done_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='done at')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('done_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='done by')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='open_items', to='projects.project', verbose_name='project')),
            ],
            options={
                'verbose_name': 'open item',
                'verbose_name_plural': 'open items',
                'ordering': ['is_done', 'created_at', 'id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='ProjectFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=200, verbose_name='title')),
                ('file', models.FileField(max_length=200, upload_to=rentalars.projects.models.project_file_path, verbose_name='file')),
                ('original_name', models.CharField(max_length=255, verbose_name='file name')),
                ('size', models.PositiveBigIntegerField(default=0, verbose_name='size')),
                ('visible_to_crew', models.BooleanField(default=False, help_text='Shown in the deployment view of the people planned.', verbose_name='visible to the crew')),
                ('uploaded_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='uploaded')),
                ('document_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='files', to='masterdata.documenttype', verbose_name='document type')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='files', to='projects.project', verbose_name='project')),
                ('source_attachment', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='project_files', to='mail.mailattachment', verbose_name='from e-mail attachment')),
                ('uploaded_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='uploaded by')),
                ('supplier', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='project_files', to='masterdata.supplier', verbose_name='supplier')),
                ('supplier_document_kind', models.CharField(blank=True, choices=[('offer', 'offer'), ('confirmation', 'order confirmation'), ('delivery', 'delivery note'), ('invoice', 'invoice'), ('other', 'other')], max_length=12, verbose_name='kind of document')),
                ('show_system', models.CharField(blank=True, help_text='e.g. grandMA3, Eos, Resolume Arena, DM7.', max_length=80, verbose_name='console or software')),
                ('show_version', models.CharField(blank=True, help_text='The version the show was saved with.', max_length=40, verbose_name='software version')),
                ('is_current_show', models.BooleanField(default=False, help_text='The show file to load; earlier ones of the same console stay as they are.', verbose_name='current show')),
            ],
            options={
                'verbose_name': 'project file',
                'verbose_name_plural': 'project files',
                'ordering': ['-uploaded_at', '-id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='ProjectPhase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('planning', 'Planning and meetings'), ('loading', 'Packing'), ('travel', 'Travel'), ('setup', 'Setup'), ('rehearsal', 'Rehearsal'), ('event', 'Event'), ('teardown', 'Teardown'), ('return', 'Return'), ('aftercare', 'Follow-up work'), ('cleaning', 'Cleaning'), ('other', 'Other')], default='setup', max_length=12, verbose_name='phase')),
                ('title', models.CharField(blank=True, help_text='Optional, e.g. “Setup hall 3”.', max_length=120, verbose_name='label')),
                ('start', models.DateTimeField(verbose_name='from')),
                ('end', models.DateTimeField(verbose_name='until')),
                ('location', models.CharField(blank=True, help_text='If not a venue of the master data.', max_length=250, verbose_name='place')),
                ('notes', models.TextField(blank=True, verbose_name='notes')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='phases', to='projects.project', verbose_name='project')),
                ('venue_site', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='phases', to='customers.venue', verbose_name='venue from the master data')),
            ],
            options={
                'verbose_name': 'phase',
                'verbose_name_plural': 'phases',
                'ordering': ['start', 'id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='ProjectTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('content', models.JSONField(default=dict, editable=False, verbose_name='content')),
                ('source_number', models.CharField(blank=True, editable=False, max_length=30, verbose_name='made from project')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='created by')),
            ],
            options={
                'verbose_name': 'project template',
                'verbose_name_plural': 'project templates',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='ServiceCaseParticipant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note', models.CharField(blank=True, max_length=250, verbose_name='note')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='added')),
                ('added_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='added by')),
                ('job_function', models.ForeignKey(blank=True, help_text='Optional – what the person does in the case.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_case_participations', to='personnel.jobfunction', verbose_name='job function')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='service_case_participations', to='personnel.person', verbose_name='person')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='participants', to='projects.project', verbose_name='service case')),
            ],
            options={
                'verbose_name': 'person taking part',
                'verbose_name_plural': 'people taking part',
                'ordering': ['created_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('project', 'person'), name='service_case_participant_unique')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='TripAdjustment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trip_key', models.CharField(blank=True, help_text='Empty: a trip of its own, added by hand.', max_length=40, verbose_name='trip')),
                ('is_removed', models.BooleanField(default=False, verbose_name='removed')),
                ('title', models.CharField(blank=True, max_length=120, verbose_name='title')),
                ('start', models.DateTimeField(blank=True, null=True, verbose_name='departure')),
                ('origin', models.CharField(blank=True, max_length=250, verbose_name='start')),
                ('stops', models.JSONField(blank=True, null=True, verbose_name='stops')),
                ('destination', models.CharField(blank=True, max_length=250, verbose_name='destination')),
                ('note', models.CharField(blank=True, max_length=500, verbose_name='note')),
                ('changed_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='changed')),
                ('changed_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='changed by')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trip_adjustments', to='projects.project', verbose_name='project')),
            ],
            options={
                'verbose_name': 'changed trip',
                'verbose_name_plural': 'changed trips',
                'ordering': ['id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='VehicleLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='title')),
                ('position', models.PositiveIntegerField(default=0, verbose_name='position')),
                ('start', models.DateTimeField(verbose_name='from')),
                ('end', models.DateTimeField(verbose_name='until')),
                ('note', models.TextField(blank=True, verbose_name='note')),
                ('billing', models.CharField(choices=[('km', 'per kilometre'), ('day', 'per day')], default='km', max_length=4, verbose_name='billing')),
                ('price_per_km', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='price per kilometre')),
                ('trailer_surcharge_per_km', models.DecimalField(decimal_places=2, default=Decimal('0'), help_text='Added to the price per kilometre on every trip with a trailer.', max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='trailer surcharge per kilometre')),
                ('price_per_day', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='price per day')),
                ('rental_days', models.PositiveSmallIntegerField(blank=True, help_text="Empty: as material – the days of the booking's own period, else the project's rental days.", null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(999)], verbose_name='rental days')),
                ('only_trip_days', models.BooleanField(default=False, help_text='Per day: count only the days on which the trailer drives, not the rental days.', verbose_name='only days with trips')),
                ('discount_percent', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='discount in percent')),
                ('cost_per_km', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='internal cost per kilometre')),
                ('cost_per_day', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='internal cost per day')),
                ('subrental_cost', models.DecimalField(blank=True, decimal_places=2, help_text='For the whole booking; it is the cost instead of the costs per kilometre and day.', max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='what the supplier charges')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('item', models.ForeignKey(blank=True, help_text='Empty: not chosen yet, or from a supplier.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='vehicle_lines', to='material.materialitem', verbose_name='vehicle')),
                ('phase', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vehicle_lines', to='projects.projectphase', verbose_name='phase')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='vehicle_lines', to='products.product', verbose_name='vehicle product')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vehicle_lines', to='projects.project', verbose_name='project')),
                ('scale_version', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='vehicle_lines', to='masterdata.rentalscaleversion', verbose_name='rental scale')),
                ('supplier', models.ForeignKey(blank=True, help_text='Only for a vehicle from a supplier.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='vehicle_lines', to='masterdata.supplier', verbose_name='supplier')),
                ('tax_rate', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='vehicle_lines', to='masterdata.taxrate', verbose_name='tax rate')),
            ],
            options={
                'verbose_name': 'vehicle booking',
                'verbose_name_plural': 'vehicle bookings',
                'ordering': ['position', 'id'],
                'indexes': [models.Index(fields=['item', 'start', 'end'], name='vehicle_line_period_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='TripVehicle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trip_key', models.CharField(max_length=40, verbose_name='trip')),
                ('planned_km', models.DecimalField(blank=True, decimal_places=1, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='planned kilometres')),
                ('driven_km', models.DecimalField(blank=True, decimal_places=1, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='driven kilometres')),
                ('billing', models.CharField(choices=[('driven', 'driven kilometres'), ('planned', 'planned kilometres'), ('flat', 'flat rate for the trip')], default='driven', max_length=8, verbose_name='charged')),
                ('flat_price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='flat rate for the trip')),
                ('note', models.CharField(blank=True, max_length=500, verbose_name='note')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trip_vehicles', to='projects.project', verbose_name='project')),
                ('trailer_line', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='trailer_uses', to='projects.vehicleline', verbose_name='trailer')),
                ('vehicle_line', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trip_uses', to='projects.vehicleline', verbose_name='vehicle')),
            ],
            options={
                'verbose_name': 'vehicle on a trip',
                'verbose_name_plural': 'vehicles on trips',
                'ordering': ['id'],
                'indexes': [],
                'constraints': [models.UniqueConstraint(fields=('vehicle_line', 'trip_key'), name='trip_vehicle_once_per_trip', violation_error_message='This vehicle drives this trip already.')],
            },
        ),
        migrations.AlterField(
            model_name='crewline',
            name='billing',
            field=models.CharField(choices=[('plan', 'by plan'), ('flat', 'flat rate'), ('effort', 'by effort'), ('day', 'per day')], default='plan', max_length=10, verbose_name='billing'),
        ),
        migrations.AlterField(
            model_name='crewline',
            name='unit_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), help_text='Per hour; with “per day” per day; with “flat rate” the price of the whole deployment.', max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='price'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='answer_note',
            field=models.CharField(blank=True, max_length=250, verbose_name='answer'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='answered_at',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='answered at'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='request_status',
            field=models.CharField(blank=True, choices=[('', 'not asked'), ('requested', 'asked'), ('accepted', 'accepted'), ('declined', 'declined')], default='', max_length=10, verbose_name='request'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='requested_at',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='asked at'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='requested_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='asked by'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='discount_percent',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='discount in percent'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='list_price',
            field=models.DecimalField(blank=True, decimal_places=2, editable=False, max_digits=10, null=True, verbose_name='price of the product when taken over'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='daily_rate',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Internal cost per day, copied from the person when assigned; used with “per day”.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='day rate'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='days',
            field=models.PositiveSmallIntegerField(blank=True, help_text='Charged with “per day”. Empty: the calendar days of the period.', null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(999)], verbose_name='days'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='phase',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='crew_lines', to='projects.projectphase', verbose_name='phase'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='requested_start',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='asked for from'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='requested_end',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='asked for until'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='hours_limit',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='The hours of one day beyond this cost the price from the limit. Empty: every hour the same.', max_digits=4, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.25')), django.core.validators.MaxValueValidator(Decimal('23.75'))], verbose_name='limit in hours per day'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='unit_price_above_limit',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='price per hour from the limit'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='hourly_rate_above_limit',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Internal cost of an hour beyond the limit, copied from the person when assigned.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='hourly rate from the limit'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='time_surcharges_on_price',
            field=models.BooleanField(default=False, help_text='Only by plan or by effort. The percentages are set under Settings → Surcharges.', verbose_name='surcharges for night, Sunday and holidays on the price'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='time_surcharges_on_cost',
            field=models.BooleanField(default=False, help_text='Only by plan or by effort, not with a flat rate for the person.', verbose_name='surcharges for night, Sunday and holidays on the costs'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='is_driver',
            field=models.BooleanField(default=False, verbose_name='driver'),
        ),
        migrations.AddField(
            model_name='crewline',
            name='vehicle_line',
            field=models.ForeignKey(blank=True, help_text='The vehicle of this project the person travels with.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='crew_lines', to='projects.vehicleline', verbose_name='vehicle'),
        ),
        migrations.AddField(
            model_name='group',
            name='alternative_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='alternatives', to='projects.group', verbose_name='alternative to'),
        ),
        migrations.AlterField(
            model_name='materialline',
            name='subrental_status',
            field=models.CharField(blank=True, choices=[('open', 'open'), ('requested', 'requested'), ('ordered', 'ordered'), ('received', 'received'), ('returned', 'returned')], max_length=12, verbose_name='subrental status'),
        ),
        migrations.AddField(
            model_name='materialline',
            name='is_addendum',
            field=models.BooleanField(default=False, editable=False, verbose_name='added while packing'),
        ),
        migrations.AddField(
            model_name='materialline',
            name='list_price',
            field=models.DecimalField(blank=True, decimal_places=2, editable=False, max_digits=10, null=True, verbose_name='price of the product when taken over'),
        ),
        migrations.AddField(
            model_name='materialline',
            name='variant',
            field=models.CharField(blank=True, choices=[('', 'normal'), ('optional', 'optional'), ('alternative', 'alternative')], default='', help_text='Optional and alternative lines are shown with their price, but not added to the total.', max_length=12, verbose_name='counts as'),
        ),
        migrations.AddField(
            model_name='materialline',
            name='taken_over_from',
            field=models.ForeignKey(blank=True, help_text='The pieces come straight from this line of another subproject, not from the warehouse. They are charged only once, on that line.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='taken_over_by', to='projects.materialline', verbose_name='taken over from'),
        ),
        migrations.AddField(
            model_name='materialline',
            name='alternative_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='alternatives', to='projects.materialline', verbose_name='alternative to'),
        ),
        migrations.AddField(
            model_name='materialline',
            name='picked_up_at_supplier',
            field=models.BooleanField(default=False, help_text='Off: the supplier delivers and collects.', verbose_name='picked up at the supplier'),
        ),
        migrations.AddField(
            model_name='project',
            name='venue_site',
            field=models.ForeignKey(blank=True, help_text='With address, contact on site and notes.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='projects', to='customers.venue', verbose_name='venue from the master data'),
        ),
        migrations.AddField(
            model_name='project',
            name='billing_address',
            field=models.ForeignKey(blank=True, help_text='Empty: the address of the customer.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='customers.customeraddress', verbose_name='billing address'),
        ),
        migrations.AddField(
            model_name='project',
            name='delivery_address',
            field=models.ForeignKey(blank=True, help_text='For the delivery note. Empty: the venue, else the address of the customer.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='customers.customeraddress', verbose_name='delivery address'),
        ),
        migrations.AddField(
            model_name='project',
            name='former_number',
            field=models.CharField(blank=True, db_index=True, editable=False, help_text='The number before an update renumbered the project; it still finds the project.', max_length=30, verbose_name='former project number'),
        ),
        migrations.AddField(
            model_name='project',
            name='follow_up_on',
            field=models.DateField(blank=True, db_index=True, editable=False, null=True, verbose_name='follow-up on'),
        ),
        migrations.AddField(
            model_name='project',
            name='follow_up_note',
            field=models.CharField(blank=True, editable=False, max_length=250, verbose_name='note on the follow-up'),
        ),
        migrations.AddField(
            model_name='project',
            name='follow_up_user',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='follow_up_projects', to=settings.AUTH_USER_MODEL, verbose_name='follow-up for'),
        ),
        migrations.AddField(
            model_name='project',
            name='follow_up_notified_at',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='follow-up notified at'),
        ),
        migrations.AddField(
            model_name='project',
            name='kind',
            field=models.CharField(choices=[('project', 'project'), ('service_case', 'service case')], default='project', editable=False, max_length=14, verbose_name='kind'),
        ),
        migrations.AddField(
            model_name='project',
            name='case_status',
            field=models.CharField(blank=True, choices=[('open', 'Open'), ('in_progress', 'In progress'), ('waiting', 'Waiting'), ('closing', 'Waiting to close'), ('backlog', 'Backlog'), ('done', 'Done')], editable=False, max_length=12, verbose_name='status of the service case'),
        ),
        migrations.AddField(
            model_name='project',
            name='case_contact',
            field=models.CharField(blank=True, help_text='Name, phone or e-mail address of whoever reported it, if not a contact of the customer.', max_length=250, verbose_name='reported by'),
        ),
        migrations.AddField(
            model_name='project',
            name='follow_up_at',
            field=models.TimeField(blank=True, editable=False, null=True, verbose_name='follow-up at'),
        ),
        migrations.AddField(
            model_name='project',
            name='case_waiting_for',
            field=models.CharField(blank=True, choices=[('reply', 'A reply'), ('action', 'An action'), ('delivery', 'A delivery of material')], editable=False, max_length=10, verbose_name='waiting for'),
        ),
        migrations.AddField(
            model_name='project',
            name='field_changed_at',
            field=models.JSONField(blank=True, default=dict, editable=False, verbose_name='times of change per field'),
        ),
        migrations.AddField(
            model_name='project',
            name='invoice_status',
            field=models.CharField(blank=True, choices=[('', 'open'), ('issued', 'invoice issued'), ('not_needed', 'no invoice'), ('earlier', 'closed earlier')], default='', max_length=12, verbose_name='invoice'),
        ),
        migrations.AddField(
            model_name='project',
            name='source_defect',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_cases', to='material.defectreport', verbose_name='made of the defect report'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['kind', 'case_status'], name='project_kind_case_status_idx'),
        ),
        migrations.AlterField(
            model_name='projectmembership',
            name='level',
            field=models.CharField(choices=[('none', 'no access'), ('deployment', 'deployment view'), ('read', 'read'), ('edit', 'edit')], default='read', max_length=12),
        ),
    ]
