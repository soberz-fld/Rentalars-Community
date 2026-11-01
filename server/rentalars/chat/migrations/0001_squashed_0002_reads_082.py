# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``chat`` from 0001_initial to 0002_reads_082 in one.

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

    replaces = [('chat', '0001_initial'), ('chat', '0002_reads_082')]

    initial = True

    dependencies = [
        ('projects', '0001_squashed_0003_internal_projects_and_crew_lines'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('author_name', models.CharField(blank=True, max_length=150, verbose_name='name of the author')),
                ('text', models.TextField(max_length=4000, verbose_name='message')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='written')),
                ('edited_at', models.DateTimeField(blank=True, null=True, verbose_name='changed')),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='author')),
                ('mentioned', models.ManyToManyField(blank=True, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='mentioned')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_messages', to='projects.project', verbose_name='project')),
                ('revision', models.PositiveIntegerField(default=0, editable=False)),
            ],
            options={
                'verbose_name': 'chat message',
                'verbose_name_plural': 'chat messages',
                'ordering': ['created_at', 'id'],
                'indexes': [models.Index(fields=['project', 'id'], name='chat_project_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='ChatReadMark',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_read_id', models.BigIntegerField(default=0)),
                ('read_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='projects.project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'read chat',
                'verbose_name_plural': 'read chats',
                'constraints': [models.UniqueConstraint(fields=('user', 'project'), name='chat_read_once')],
                'indexes': [],
            },
        ),
    ]
