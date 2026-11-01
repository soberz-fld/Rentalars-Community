# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``timetracking`` from 0001_initial to 0005_shares_081 in one.

Squashed: a new database is built from here, and a database that has applied the replaced
migrations counts it as applied (``replaces``). Data steps that only converted the data of older
versions are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.timetracking.models
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('timetracking', '0001_initial'), ('timetracking', '0002_entry_without_project'), ('timetracking', '0003_expenses_080'), ('timetracking', '0004_expenses_081'), ('timetracking', '0005_shares_081')]

    initial = True

    dependencies = [
        ('personnel', '0001_squashed_0014_licence_classes_090'),
        ('projects', '0001_squashed_0003_internal_projects_and_crew_lines'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TimeEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start', models.DateTimeField(verbose_name='start')),
                ('end', models.DateTimeField(blank=True, null=True, verbose_name='end')),
                ('break_minutes', models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(600)], verbose_name='break in minutes')),
                ('hours', models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=6, verbose_name='hours')),
                ('note', models.CharField(blank=True, max_length=250, verbose_name='note')),
                ('hourly_rate', models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=8, verbose_name='hourly rate')),
                ('status', models.CharField(choices=[('recorded', 'recorded'), ('submitted', 'submitted'), ('approved', 'approved'), ('rejected', 'rejected')], default='recorded', max_length=10, verbose_name='status')),
                ('submitted_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='submitted')),
                ('decided_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='decided')),
                ('rejection_reason', models.CharField(blank=True, max_length=250, verbose_name='reason for rejection')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('crew_line', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='time_entries', to='projects.crewline', verbose_name='crew line')),
                ('decided_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='decided by')),
                ('job_function', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='time_entries', to='personnel.jobfunction', verbose_name='job function')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='time_entries', to='personnel.person', verbose_name='person')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='time_entries', to='projects.project', verbose_name='project')),
                ('period_key', models.UUIDField(blank=True, db_index=True, editable=False, null=True, verbose_name='period')),
            ],
            options={
                'verbose_name': 'time entry',
                'verbose_name_plural': 'time entries',
                'ordering': ['-start', '-id'],
                'indexes': [models.Index(fields=['person', 'start', 'end'], name='time_person_period_idx'), models.Index(fields=['project', 'status'], name='time_project_status_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Expense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('meals', 'Meals'), ('travel', 'Travel'), ('lodging', 'Accommodation'), ('parking', 'Parking and tolls'), ('other', 'Other')], default='meals', max_length=10, verbose_name='kind')),
                ('date', models.DateField(verbose_name='date')),
                ('kilometres', models.DecimalField(blank=True, decimal_places=1, max_digits=7, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.1')), django.core.validators.MaxValueValidator(Decimal('20000'))], verbose_name='kilometres')),
                ('km_rate', models.DecimalField(blank=True, decimal_places=2, editable=False, max_digits=5, null=True, verbose_name='rate per kilometre')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=9, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('99999.99'))], verbose_name='amount')),
                ('note', models.CharField(blank=True, max_length=250, verbose_name='note')),
                ('receipt', models.FileField(blank=True, max_length=200, upload_to=rentalars.timetracking.models.receipt_path, verbose_name='receipt')),
                ('status', models.CharField(choices=[('recorded', 'recorded'), ('submitted', 'submitted'), ('approved', 'approved'), ('rejected', 'rejected')], default='recorded', max_length=10, verbose_name='status')),
                ('submitted_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='submitted')),
                ('decided_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='decided')),
                ('rejection_reason', models.CharField(blank=True, max_length=250, verbose_name='reason for rejection')),
                ('reimbursed_on', models.DateField(blank=True, editable=False, null=True, verbose_name='reimbursed on')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('decided_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='decided by')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='expenses', to='personnel.person', verbose_name='person')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='expenses', to='projects.project', verbose_name='project')),
                ('reimbursed_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='reimbursed by')),
                ('commute_km', models.DecimalField(blank=True, decimal_places=1, editable=False, max_digits=7, null=True, verbose_name='way to work deducted (km)')),
            ],
            options={
                'verbose_name': 'expense',
                'verbose_name_plural': 'expenses',
                'ordering': ['-date', '-id'],
                'indexes': [models.Index(fields=['person', 'date'], name='expense_person_date_idx'), models.Index(fields=['project', 'status'], name='expense_project_status_idx')],
                'constraints': [],
            },
        ),
    ]
