# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstellungen → Automationen: the rules and their runs (ADM-013).

Reading needs the module "administration" (settings); creating, changing and
deleting rules needs write access to it, as for every setting. (ADM-019)
The rules that come with Rentalars are no exception;
restoring the missing ones needs the same write access.
"""

from __future__ import annotations

import json
from typing import Any

from django.contrib import messages
from django.db.models import Count, Max, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.automations import defaults, engine
from rentalars.automations.forms import AutomationForm
from rentalars.automations.list_tables import RULE_TABLE, RUN_TABLE
from rentalars.automations.models import (
    ACTIONS_OF,
    RECIPIENTS_OF,
    Automation,
    AutomationRun,
    RunStatus,
    Trigger,
)
from rentalars.core.listing import paginate


def _rules() -> Any:
    return (
        Automation.objects.select_related("mailbox", "user")
        .annotate(
            run_count=Count("runs"),
            failed_count=Count("runs", filter=Q(runs__status=RunStatus.FAILED)),
            last_run=Max("runs__created_at"),
        )
        .order_by("name", "pk")
    )


@module_required(Module.ADMINISTRATION)
def automation_list(request: HttpRequest) -> HttpResponse:
    """The rules, and below them every run with its result (ADM-013)."""
    runs = AutomationRun.objects.select_related("project", "automation").order_by("-created_at", "-pk")
    chosen = request.GET.get("automation", "")
    if chosen.isdigit():
        runs = runs.filter(automation_id=int(chosen))
    status = request.GET.get("status", "")
    if status in RunStatus.values:
        runs = runs.filter(status=status)
    # UIX-040: rules and runs as tables of core.tables; the runs with the prefix "runs_" in the address.
    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    rule_table = RULE_TABLE.state(request)
    run_table = RUN_TABLE.state(request)
    if rule_table.wants_csv:
        return rule_table.csv_response(rule_table.order(_rules()), _("Automations"))
    runs = run_table.order(runs)
    if run_table.wants_csv:
        return run_table.csv_response(runs, _("Runs of the automations"))
    rules = list(rule_table.order(_rules()))
    for rule in rules:
        rule.can_write = can_write  # the name links to the form only for who may change it
    page = paginate(request, runs)
    # ADM-019: "Standard-Automationen wiederherstellen" only while one is missing; the question
    # names what it creates.
    missing = [default.name() for default in defaults.missing()] if can_write else []
    return render(
        request,
        "automations/list.html",
        {
            "rules": rules,
            "rule_table": rule_table,
            "rule_rows": rule_table.rows(rules),
            "run_table": run_table,
            "run_rows": run_table.rows(page),
            "page": page,
            "chosen": chosen,
            "status": status,
            "statuses": RunStatus.choices,
            "can_write": request_rights(request).can_write(Module.ADMINISTRATION),
            "missing_defaults": missing,
            "restore_question": _restore_question(missing),
        },
    )


def _quoted(names: list[str]) -> str:
    """Names in the quotation marks of the reader's language, joined: „A“, „B“."""
    return ", ".join(_("“%(name)s”") % {"name": name} for name in names)


def _restore_question(names: list[str]) -> str:
    """(ADM-019) The question before restoring: what is created, and that the rest stays."""
    if not names:
        return ""
    return _(
        "Restore the default automations? Rentalars creates: %(names)s. "
        "The automations that are there – changed or not – stay as they are."
    ) % {"names": _quoted(names)}


def _form_context(form: AutomationForm, rule: Automation | None) -> dict[str, Any]:
    triggers = [
        {"value": trigger.value, "label": trigger.label, "placeholders": engine.placeholders_of(trigger.value)}
        for trigger in Trigger
    ]
    return {
        "form": form,
        "rule": rule,
        "triggers": triggers,
        # app.js offers only the actions and recipients that fit the chosen trigger.
        "actions_of_json": json.dumps(
            {str(trigger): [str(item) for item in items] for trigger, items in ACTIONS_OF.items()}
        ),
        "recipients_of_json": json.dumps(
            {str(trigger): [str(item) for item in items] for trigger, items in RECIPIENTS_OF.items()}
        ),
    }


@module_required(Module.ADMINISTRATION, Level.WRITE)
def automation_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or change a rule."""
    rule = get_object_or_404(Automation, pk=pk) if pk is not None else None
    # ADM-019: a default is changed like any rule (and audited alike); the page says that it
    # came with Rentalars and whether it was changed – as stored, before the form fills in what was sent.
    changed = rule is not None and rule.default_changed
    form = AutomationForm(request.POST or None, instance=rule)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if saved.pk is None:
            saved.created_by = request.user
        saved.save()
        messages.success(request, _("The automation “%(name)s” is saved.") % {"name": saved.name})
        return redirect("automations:list")
    return render(request, "automations/form.html", {**_form_context(form, rule), "default_changed": changed})


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def automation_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a rule; its runs stay in the list with its name."""
    rule = get_object_or_404(Automation, pk=pk)
    name, was_default = rule.name, rule.is_default
    rule.delete()
    if was_default:
        # ADM-019: deleted like any rule; the way back is on the list.
        messages.success(
            request,
            _(
                "The automation “%(name)s” is deleted. Its runs stay listed. "
                "“Restore default automations” brings it back as it came."
            )
            % {"name": name},
        )
    else:
        messages.success(request, _("The automation “%(name)s” is deleted. Its runs stay listed.") % {"name": name})
    return redirect("automations:list")


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def automation_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    """Switch a rule on or off."""
    rule = get_object_or_404(Automation, pk=pk)
    rule.is_active = not rule.is_active
    rule.save()
    if rule.is_active:
        messages.success(request, _("The automation “%(name)s” is switched on.") % {"name": rule.name})
    else:
        messages.success(request, _("The automation “%(name)s” is switched off.") % {"name": rule.name})
    return redirect("automations:list")


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def automation_restore_defaults(request: HttpRequest) -> HttpResponse:
    """(ADM-019) Create the missing defaults by their key; leave every rule that is there alone."""
    created = defaults.restore(user=request.user)
    if created:
        messages.success(
            request,
            ngettext(
                "Restored %(count)d default automation: %(names)s. The others stay as they are.",
                "Restored %(count)d default automations: %(names)s. The others stay as they are.",
                len(created),
            )
            % {"count": len(created), "names": _quoted([rule.name for rule in created])},
        )
    else:
        messages.info(request, _("All default automations are there; nothing was created."))
    return redirect("automations:list")
