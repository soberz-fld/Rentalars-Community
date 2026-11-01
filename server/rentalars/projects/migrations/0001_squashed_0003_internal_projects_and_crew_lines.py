# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``projects`` from 0001_initial to 0003_internal_projects_and_crew_lines in one.

Squashed: a new database is built from here, and a database that has applied the replaced
migrations counts it as applied (``replaces``). Data steps that only converted the data of older
versions are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('projects', '0001_initial'), ('projects', '0002_line_preferred_material'), ('projects', '0003_internal_projects_and_crew_lines')]

    initial = True

    dependencies = [
        ('customers', '0001_squashed_0007_maps_080'),
        ('masterdata', '0001_squashed_0012_fleet_090'),
        ('material', '0001_squashed_0006_vehicles_090'),
        ('personnel', '0001_squashed_0014_licence_classes_090'),
        ('products', '0001_squashed_0008_vehicles_090'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Group',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('position', models.PositiveIntegerField(default=0, verbose_name='position')),
                ('kind', models.CharField(choices=[('normal', 'normal'), ('optional', 'optional'), ('alternative', 'alternative')], default='normal', max_length=12, verbose_name='counts as')),
                ('discount_percent', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='discount in percent')),
                ('discount_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='discount as amount')),
                ('flat_price', models.DecimalField(blank=True, decimal_places=2, help_text='Replaces the sum of the lines.', max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='flat price')),
                ('rental_days', models.PositiveSmallIntegerField(blank=True, help_text='Empty: as the project.', null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(999)], verbose_name='rental days')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='projects.group', verbose_name='parent group')),
            ],
            options={
                'verbose_name': 'group',
                'verbose_name_plural': 'groups',
                'ordering': ['position', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(editable=False, max_length=30, unique=True, verbose_name='project number')),
                ('name', models.CharField(max_length=200, verbose_name='name')),
                ('venue', models.CharField(blank=True, max_length=250, verbose_name='venue')),
                ('status', models.CharField(choices=[('inquiry', 'Inquiry'), ('option', 'Option'), ('confirmed_open', 'Confirmed – details open'), ('confirmed', 'Confirmed'), ('out', 'Out'), ('returned', 'Returned'), ('closed', 'Closed'), ('cancelled', 'Cancelled')], default='inquiry', max_length=20, verbose_name='status')),
                ('start', models.DateTimeField(verbose_name='material out from')),
                ('end', models.DateTimeField(verbose_name='material back by')),
                ('event_start', models.DateTimeField(blank=True, null=True, verbose_name='event from')),
                ('event_end', models.DateTimeField(blank=True, null=True, verbose_name='event until')),
                ('rental_days', models.PositiveSmallIntegerField(blank=True, help_text='Days charged for daily rental. Empty: suggested from the event period.', null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(999)], verbose_name='rental days')),
                ('notes', models.TextField(blank=True, verbose_name='notes')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('contact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='projects', to='customers.contact', verbose_name='contact')),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='projects', to='customers.customer', verbose_name='customer')),
                ('manager', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='managed_projects', to=settings.AUTH_USER_MODEL, verbose_name='project manager')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='subprojects', to='projects.project', verbose_name='part of project')),
                ('is_internal', models.BooleanField(default=False, help_text='For times without a customer: warehouse, workshop, office. Everybody who records times can book on it.', verbose_name='internal project')),
            ],
            options={
                'verbose_name': 'project',
                'verbose_name_plural': 'projects',
                'ordering': ['-start', '-id'],
                'indexes': [models.Index(fields=['status', 'start', 'end'], name='project_status_period_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='MaterialLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='title')),
                ('quantity', models.DecimalField(decimal_places=2, default=Decimal('1'), max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='quantity')),
                ('start', models.DateTimeField(verbose_name='from')),
                ('end', models.DateTimeField(verbose_name='until')),
                ('position', models.PositiveIntegerField(default=0, verbose_name='position')),
                ('note', models.TextField(blank=True, verbose_name='note')),
                ('is_sale', models.BooleanField(default=False, verbose_name='sale')),
                ('billing_mode', models.CharField(choices=[('daily_piece', 'daily rental per piece'), ('daily_kit', 'daily rental per kit'), ('flat', 'flat'), ('hourly', 'by the hour'), ('effort', 'by effort')], default='flat', max_length=20, verbose_name='billing mode')),
                ('unit_price', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10, verbose_name='unit price')),
                ('discount_percent', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='discount in percent')),
                ('hours', models.DecimalField(blank=True, decimal_places=2, help_text='For billing by the hour.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='hours')),
                ('quantity_is_estimate', models.BooleanField(default=False, help_text='For billing by effort: replace the estimate by the actual effort after the event.', verbose_name='quantity is an estimate')),
                ('rental_days', models.PositiveSmallIntegerField(blank=True, help_text='Empty: as the group or the project.', null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(999)], verbose_name='rental days')),
                ('manual_scale_factor', models.DecimalField(blank=True, decimal_places=3, max_digits=7, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='scale factor set by hand')),
                ('surcharge_percent', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('1000'))], verbose_name='surcharge in percent')),
                ('purchase_price', models.DecimalField(blank=True, decimal_places=2, help_text='What the supplier charges per unit for the whole period.', max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='purchase price per unit')),
                ('subrental_status', models.CharField(blank=True, choices=[('requested', 'requested'), ('ordered', 'ordered'), ('received', 'received'), ('returned', 'returned')], max_length=12, verbose_name='subrental status')),
                ('stock_removed_quantity', models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=10, verbose_name='already taken out of stock')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('covers_line', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='covering_lines', to='projects.materialline', verbose_name='covers shortage of')),
                ('covers_product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='products.product', verbose_name='covered product')),
                ('group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='projects.group', verbose_name='group')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='material_lines', to='products.product', verbose_name='product')),
                ('scale_version', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='material_lines', to='masterdata.rentalscaleversion', verbose_name='rental scale')),
                ('supplier', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='subrental_lines', to='masterdata.supplier', verbose_name='supplier')),
                ('tax_rate', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='material_lines', to='masterdata.taxrate', verbose_name='tax rate')),
                ('unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='masterdata.unit', verbose_name='unit')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='material_lines', to='projects.project', verbose_name='project')),
                ('preferred_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='preferring_lines', to='material.materialitem', verbose_name='specific item')),
                ('preferred_model', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='preferring_lines', to='material.materialmodel', verbose_name='specific model')),
            ],
            options={
                'verbose_name': 'material line',
                'verbose_name_plural': 'material lines',
                'ordering': ['position', 'id'],
                'indexes': [models.Index(fields=['product', 'start', 'end'], name='line_product_period_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='ProjectMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.CharField(choices=[('deployment', 'deployment view'), ('read', 'read'), ('edit', 'edit')], default='read', max_length=12)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='projects.project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'project membership',
                'verbose_name_plural': 'project memberships',
                'indexes': [],
                'constraints': [models.UniqueConstraint(fields=('project', 'user'), name='project_membership_unique')],
            },
        ),
        migrations.CreateModel(
            name='SurchargeTarget',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_type', models.CharField(choices=[('line', 'line'), ('group', 'group'), ('personnel', 'personnel'), ('project', 'whole project')], max_length=10)),
                ('surcharge_line', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='surcharge_targets', to='projects.materialline')),
                ('target_group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='projects.group')),
                ('target_line', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='projects.materialline')),
            ],
            options={
                'verbose_name': 'surcharge target',
                'verbose_name_plural': 'surcharge targets',
                'ordering': ['id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='CrewLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start', models.DateTimeField(verbose_name='from')),
                ('end', models.DateTimeField(verbose_name='until')),
                ('planned_hours', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=7, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='planned hours')),
                ('meeting_point', models.CharField(blank=True, max_length=200, verbose_name='meeting point')),
                ('note', models.TextField(blank=True, help_text='Visible to the person in the deployment view.', verbose_name='note')),
                ('position', models.PositiveIntegerField(default=0, verbose_name='position')),
                ('title', models.CharField(max_length=200, verbose_name='title')),
                ('billing', models.CharField(choices=[('plan', 'by plan'), ('flat', 'flat rate'), ('effort', 'by effort')], default='plan', max_length=10, verbose_name='billing')),
                ('unit_price', models.DecimalField(decimal_places=2, default=Decimal('0'), help_text='Per hour; with “flat rate” the price of the whole deployment.', max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='price')),
                ('hourly_rate', models.DecimalField(blank=True, decimal_places=2, help_text='Internal cost per hour, copied from the person when assigned.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='hourly rate')),
                ('cost_flat_rate', models.DecimalField(blank=True, decimal_places=2, help_text='Internal cost of the whole deployment, instead of hours × hourly rate.', max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='flat rate for the person')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('job_function', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='crew_lines', to='personnel.jobfunction', verbose_name='job function')),
                ('person', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='crew_lines', to='personnel.person', verbose_name='person')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crew_lines', to='projects.project', verbose_name='project')),
                ('service_product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='crew_lines', to='products.product', verbose_name='service product')),
                ('tax_rate', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='crew_lines', to='masterdata.taxrate', verbose_name='tax rate')),
            ],
            options={
                'verbose_name': 'crew line',
                'verbose_name_plural': 'crew lines',
                'ordering': ['start', 'position', 'id'],
                'indexes': [models.Index(fields=['person', 'start', 'end'], name='crew_person_period_idx')],
                'constraints': [],
            },
        ),
        migrations.AddField(
            model_name='group',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='groups', to='projects.project', verbose_name='project'),
        ),
    ]
