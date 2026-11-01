# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``notifications`` from 0001_initial to 0010_addresses_085 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('notifications', '0001_initial'), ('notifications', '0002_stage5'), ('notifications', '0003_calendar_problem'), ('notifications', '0004_follow_up_071'), ('notifications', '0005_chat_080'), ('notifications', '0006_expenses_080'), ('notifications', '0007_categories_081'), ('notifications', '0008_service_case_081'), ('notifications', '0009_invoice_085'), ('notifications', '0010_addresses_085')]

    initial = True

    dependencies = [
        ('products', '0001_squashed_0008_vehicles_090'),
        ('projects', '0001_squashed_0003_internal_projects_and_crew_lines'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('deployment_request', 'Deployment request'), ('deployment_answer', 'Answer to a deployment request'), ('project_change', 'Change of a project'), ('shortage', 'Shortage'), ('defect', 'Defect reported'), ('new_mail', 'New mail for a project'), ('mail_problem', 'Problem fetching mails'), ('system_error', 'Error of the application'), ('low_stock', 'Stock below the minimum'), ('inspection_due', 'Inspections due'), ('qualification_expiry', 'Qualification expiring'), ('job_finished', 'A task in the background is finished'), ('calendar_problem', 'Problem with my calendar'), ('follow_up', 'Follow-up of a project'), ('chat_mention', 'Mentioned in a project chat'), ('automation', 'Message of an automation'), ('expense', 'My expenses sent back or reimbursed'), ('service_case', 'Added to a service case'), ('invoice_reminder', 'Invoice still to be written')], max_length=24, verbose_name='kind')),
                ('title', models.CharField(max_length=250, verbose_name='title')),
                ('body', models.TextField(blank=True, verbose_name='text')),
                ('url', models.CharField(blank=True, max_length=500, verbose_name='link')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created')),
                ('read_at', models.DateTimeField(blank=True, null=True, verbose_name='read')),
                ('emailed_at', models.DateTimeField(blank=True, null=True, verbose_name='sent by e-mail')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='projects.project', verbose_name='project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL, verbose_name='user')),
                ('companion', models.BooleanField(default=False, verbose_name='in the companion app')),
            ],
            options={
                'verbose_name': 'notification',
                'verbose_name_plural': 'notifications',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['user', 'read_at'], name='notification_unread_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Preference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('deployment_request', 'Deployment request'), ('deployment_answer', 'Answer to a deployment request'), ('project_change', 'Change of a project'), ('shortage', 'Shortage'), ('defect', 'Defect reported'), ('new_mail', 'New mail for a project'), ('mail_problem', 'Problem fetching mails'), ('system_error', 'Error of the application'), ('low_stock', 'Stock below the minimum'), ('inspection_due', 'Inspections due'), ('qualification_expiry', 'Qualification expiring'), ('job_finished', 'A task in the background is finished'), ('calendar_problem', 'Problem with my calendar'), ('follow_up', 'Follow-up of a project'), ('chat_mention', 'Mentioned in a project chat'), ('automation', 'Message of an automation'), ('expense', 'My expenses sent back or reimbursed'), ('service_case', 'Added to a service case'), ('invoice_reminder', 'Invoice still to be written')], max_length=24, verbose_name='kind')),
                ('in_app', models.BooleanField(default=True, verbose_name='in the application')),
                ('by_email', models.BooleanField(default=True, verbose_name='by e-mail')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_preferences', to=settings.AUTH_USER_MODEL, verbose_name='user')),
                ('companion', models.BooleanField(default=False, verbose_name='in the companion app')),
            ],
            options={
                'verbose_name': 'notification setting',
                'verbose_name_plural': 'notification settings',
                'constraints': [models.UniqueConstraint(fields=('user', 'kind'), name='notification_preference_once')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='ShortageNotice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=0)),
                ('reported_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('line', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='projects.materialline')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='products.product')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('line', 'product'), name='shortage_notice_once')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='DueNotice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=120, unique=True)),
                ('reported_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='StockNotice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stock', models.IntegerField(default=0)),
                ('reported_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('product', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='products.product')),
            ],
            options={
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='InvoiceNotice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_reminded_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_reminded_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('count', models.PositiveIntegerField(default=1)),
                ('project', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='projects.project')),
            ],
            options={
                'indexes': [],
                'constraints': [],
            },
        ),
    ]
