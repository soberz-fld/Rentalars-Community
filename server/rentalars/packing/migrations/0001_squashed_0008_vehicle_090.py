# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``packing`` from 0001_initial to 0008_vehicle_090 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('packing', '0001_initial'), ('packing', '0002_stage5'), ('packing', '0003_handovers'), ('packing', '0004_change_times_070'), ('packing', '0005_partial_return_070'), ('packing', '0006_sync_082'), ('packing', '0007_labels_084'), ('packing', '0008_vehicle_090')]

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('material', '0001_squashed_0006_vehicles_090'),
        ('products', '0001_squashed_0008_vehicles_090'),
        ('projects', '0004_squashed_0029_logistics_090'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Packlist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, help_text='e.g. “Truck 1”, “Light”, “Thursday”.', max_length=120, verbose_name='title')),
                ('status', models.CharField(choices=[('open', 'open'), ('in_progress', 'in progress'), ('packed', 'packed'), ('partly_issued', 'partly issued'), ('issued', 'issued'), ('returned', 'returned')], default='open', max_length=14, verbose_name='status')),
                ('issued_at', models.DateTimeField(blank=True, null=True, verbose_name='issued at')),
                ('returned_at', models.DateTimeField(blank=True, null=True, verbose_name='returned at')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='packlists', to='projects.project', verbose_name='project')),
                ('returned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('loading_at', models.DateTimeField(blank=True, null=True, verbose_name='loading')),
                ('note', models.CharField(blank=True, max_length=250, verbose_name='note')),
                ('packing_started_at', models.DateTimeField(blank=True, null=True, verbose_name='packing started')),
                ('vehicle_line', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='packlists', to='projects.vehicleline', verbose_name='vehicle')),
            ],
            options={
                'verbose_name': 'packing list',
                'verbose_name_plural': 'packing lists',
                'ordering': ['project', 'id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='PackEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('packed_quantity', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10)),
                ('issued_quantity', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10)),
                ('returned_quantity', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10)),
                ('missing_resolved', models.BooleanField(default=False)),
                ('missing_note', models.CharField(blank=True, max_length=250)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('line', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pack_entries', to='projects.materialline')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='products.product')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('packlist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='packing.packlist')),
                ('required_snapshot', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('title_snapshot', models.CharField(blank=True, max_length=250)),
                ('handed_over_quantity', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10)),
                ('packed_changed_at', models.DateTimeField(blank=True, null=True)),
                ('returned_changed_at', models.DateTimeField(blank=True, null=True)),
                ('taken_back_quantity', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10)),
                ('taken_back_at', models.DateTimeField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'packing list entry',
                'verbose_name_plural': 'packing list entries',
                'indexes': [],
                'constraints': [models.UniqueConstraint(fields=('packlist', 'line', 'product'), name='pack_entry_unique')],
            },
        ),
        migrations.CreateModel(
            name='Allocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('issued_at', models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True)),
                ('returned_at', models.DateTimeField(blank=True, null=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='allocations', to='material.materialitem')),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='allocations', to='packing.packentry')),
                ('with_container', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='contents', to='packing.allocation')),
            ],
            options={
                'verbose_name': 'item allocation',
                'verbose_name_plural': 'item allocations',
                'ordering': ['-issued_at'],
            },
        ),
        migrations.CreateModel(
            name='LineAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('line', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='packlist_assignment', to='projects.materialline')),
                ('packlist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='packing.packlist')),
            ],
            options={
                'verbose_name': 'packing list assignment',
                'verbose_name_plural': 'packing list assignments',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Extraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('container', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='material.materialitem')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='extractions', to='material.materialitem')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='extractions', to='projects.project')),
            ],
            options={
                'verbose_name': 'extracted content',
                'verbose_name_plural': 'extracted contents',
                'constraints': [models.UniqueConstraint(fields=('project', 'item'), name='extraction_once_per_project')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='Handover',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10)),
                ('handed_over_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('handed_over_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='handovers_out', to='packing.packentry')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='handovers_in', to='packing.packentry')),
            ],
            options={
                'verbose_name': 'handover',
                'verbose_name_plural': 'handovers',
                'ordering': ['handed_over_at', 'id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='SyncReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('change_id', models.CharField(max_length=64)),
                ('line', models.BigIntegerField()),
                ('product', models.BigIntegerField()),
                ('field', models.CharField(max_length=10)),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10)),
                ('base_version', models.PositiveIntegerField(blank=True, null=True)),
                ('outcome', models.CharField(max_length=10)),
                ('message', models.CharField(blank=True, max_length=250)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('packlist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='packing.packlist')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('reason', models.CharField(blank=True, default='', max_length=30)),
            ],
            options={
                'verbose_name': 'synchronised change',
                'verbose_name_plural': 'synchronised changes',
                'constraints': [models.UniqueConstraint(fields=('user', 'change_id'), name='sync_receipt_once')],
                'indexes': [],
            },
        ),
        migrations.AddField(
            model_name='allocation',
            name='handover',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='allocations', to='packing.handover'),
        ),
        migrations.AddIndex(
            model_name='allocation',
            index=models.Index(fields=['item', 'returned_at'], name='allocation_item_open_idx'),
        ),
    ]
