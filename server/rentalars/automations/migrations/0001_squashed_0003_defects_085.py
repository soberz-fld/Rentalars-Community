# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``automations`` from 0001_initial to 0003_defects_085 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


#: (trigger, status of the case as condition, action, new status, German name, English name).
RULES = (
    (
        "case_follow_up",
        "closing",
        "case_status",
        "done",
        "Wartet auf Schließen: zum Termin schließen",
        "Waiting to close: close at the time set",
    ),
    (
        "case_communication",
        "closing",
        "case_status",
        "open",
        "Wartet auf Schließen: bei neuer Kommunikation wieder öffnen",
        "Waiting to close: open again on new communication",
    ),
    (
        "case_follow_up",
        "backlog",
        "case_status",
        "open",
        "Rückstand: zur Wiedervorlage wieder öffnen",
        "Backlog: open again when the follow-up is due",
    ),
)


def _english() -> bool:
    return str(getattr(settings, "LANGUAGE_CODE", "de") or "de").lower().startswith("en")


def add_default_rules(apps, schema_editor):
    """PRJ-112, ADM-013: the three rules of the service cases, active (automations 0002)."""
    rule_model = apps.get_model("automations", "Automation")
    now = timezone.now()
    for trigger, status, action, new_status, german, english in RULES:
        if rule_model.objects.filter(trigger=trigger, status=status, action=action, new_case_status=new_status).exists():
            continue
        rule_model.objects.create(
            name=english if _english() else german,
            is_active=True,
            trigger=trigger,
            status=status,
            communication="",
            action=action,
            new_case_status=new_status,
            recipient="",
            subject="",
            text="",
            created_at=now,
        )


GERMAN = "Defektmeldung → Servicefall"


ENGLISH = "Defect report → service case"


def add_default_rule(apps, schema_editor):
    """MAT-057: a defect reported makes a service case – active, changeable (automations 0003)."""
    rule_model = apps.get_model("automations", "Automation")
    if rule_model.objects.filter(trigger="defect", action="create_case").exists():
        return
    rule_model.objects.create(
        name=ENGLISH if _english() else GERMAN,
        is_active=True,
        trigger="defect",
        status="",
        communication="",
        action="create_case",
        new_case_status="",
        recipient="",
        subject="",
        text="",
        created_at=timezone.now(),
    )



class Migration(migrations.Migration):

    replaces = [('automations', '0001_initial'), ('automations', '0002_cases_083'), ('automations', '0003_defects_085')]

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('mail', '0001_squashed_0013_senders_signatures_inquiries_090'),
        ('projects', '0001_squashed_0003_internal_projects_and_crew_lines'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Automation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Shown in the list and with every run.', max_length=120, verbose_name='name')),
                ('is_active', models.BooleanField(default=True, help_text='Switched off, the rule does nothing.', verbose_name='active')),
                ('trigger', models.CharField(choices=[('inquiry', 'a mail without project tag arrives'), ('project_status', 'a project reaches a status'), ('crew_answer', 'an answer to a deployment request arrives'), ('follow_up', 'a follow-up is due'), ('case_follow_up', 'the follow-up of a service case is due'), ('case_communication', 'new communication in a service case'), ('defect', 'a defect is reported')], max_length=20, verbose_name='if')),
                ('status', models.CharField(blank=True, max_length=20, verbose_name='status')),
                ('answer', models.CharField(blank=True, choices=[('', 'acceptance or refusal'), ('accepted', 'acceptance'), ('declined', 'refusal')], default='', max_length=10, verbose_name='answer')),
                ('action', models.CharField(choices=[('reply', 'answer the mail'), ('notify', 'notify a person'), ('open_item', 'note an open item in the project'), ('case_status', 'set the status of the service case'), ('create_case', 'create a service case'), ('create_inquiry', 'put it under Projects → Inquiries')], max_length=20, verbose_name='then')),
                ('recipient', models.CharField(blank=True, choices=[('user', 'a chosen user'), ('manager', 'the project manager'), ('asked_by', 'who asked for the deployment'), ('follow_up_user', 'whom the follow-up is for')], default='user', max_length=20, verbose_name='whom')),
                ('subject', models.CharField(blank=True, max_length=250, verbose_name='subject')),
                ('text', models.TextField(blank=True, verbose_name='text')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='created by')),
                ('mailbox', models.ForeignKey(blank=True, help_text='Empty: every mailbox that takes in mails without project tag.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='mail.mailbox', verbose_name='only in the mailbox')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='user')),
                ('communication', models.CharField(blank=True, choices=[('', 'a mail received or sent, or a chat message'), ('mail_in', 'a mail received'), ('mail_out', 'a mail sent'), ('chat', 'a chat message')], default='', max_length=10, verbose_name='communication')),
                ('new_case_status', models.CharField(blank=True, max_length=12, verbose_name='new status')),
            ],
            options={
                'verbose_name': 'automation',
                'verbose_name_plural': 'automations',
                'ordering': ['name', 'id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='AutomationRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('automation_name', models.CharField(max_length=120, verbose_name='name of the automation')),
                ('trigger', models.CharField(choices=[('inquiry', 'a mail without project tag arrives'), ('project_status', 'a project reaches a status'), ('crew_answer', 'an answer to a deployment request arrives'), ('follow_up', 'a follow-up is due'), ('case_follow_up', 'the follow-up of a service case is due'), ('case_communication', 'new communication in a service case'), ('defect', 'a defect is reported')], max_length=20, verbose_name='if')),
                ('action', models.CharField(choices=[('reply', 'answer the mail'), ('notify', 'notify a person'), ('open_item', 'note an open item in the project'), ('case_status', 'set the status of the service case'), ('create_case', 'create a service case'), ('create_inquiry', 'put it under Projects → Inquiries')], max_length=20, verbose_name='then')),
                ('event_key', models.CharField(max_length=120)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='time')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='finished')),
                ('status', models.CharField(choices=[('pending', 'waiting'), ('running', 'running'), ('done', 'done'), ('skipped', 'left out'), ('failed', 'failed')], default='pending', max_length=10, verbose_name='result')),
                ('event', models.CharField(blank=True, max_length=300, verbose_name='event')),
                ('recipient', models.CharField(blank=True, max_length=300, verbose_name='recipient')),
                ('detail', models.TextField(blank=True, verbose_name='detail')),
                ('data', models.JSONField(blank=True, default=dict)),
                ('automation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='runs', to='automations.automation', verbose_name='automation')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='projects.project', verbose_name='project')),
            ],
            options={
                'verbose_name': 'run of an automation',
                'verbose_name_plural': 'runs of automations',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['status', 'created_at'], name='automation_run_status_idx')],
                'constraints': [models.UniqueConstraint(fields=('automation', 'event_key'), name='automation_run_once')],
            },
        ),
        migrations.RunPython(add_default_rules, migrations.RunPython.noop),
        migrations.RunPython(add_default_rule, migrations.RunPython.noop),
    ]
