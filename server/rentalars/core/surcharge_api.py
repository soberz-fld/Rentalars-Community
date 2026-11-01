# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the surcharges for night, Sunday and holidays (PER-009, PER-040, API-002).

They apply to crew lines billed by the hour only – never to material,
incidental costs or any other line of a project (PER-009);
a product that is not a service has ``time_surcharges: null``.

* ``GET/PATCH /settings/surcharges`` – the settings of Einstellungen →
  Zuschläge: switches for new crew lines, the holidays (statutory ones of
  Germany on/off, federal state, own holidays), ``next_day_until`` and the
  list of rules. Sending ``rules`` (or ``own_holidays``) replaces the list:
  an item with the ``id`` of an existing rule changes it, one without makes a
  new rule, a rule left out is deleted; the order of the list is the order of
  the rules. Needs the module "Einstellungen".
* ``POST /settings/surcharges/section-3b`` – "Nach § 3b EStG einstellen": the
  rules of the law replace the list; the holidays stay.
* ``GET /holidays?year=2026&state=BY`` – the holidays Rentalars computes for
  a year: the statutory ones of a federal state (without ``state`` those of
  the settings, none if they are switched off there) and the own ones. For
  everybody logged in: holidays are no secret.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from rentalars.accounts.rights import Module
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, RightsViewMixin, body_of
from rentalars.core.holidays import STATES, calendar_of, holidays_of, state_label
from rentalars.core.models import OwnHoliday, TimeSurchargeRule, TimeSurchargeSettings
from rentalars.core.surcharge_views import HOLIDAY_FIELDS, RULE_FIELDS, SETTING_FIELDS
from rentalars.core.surcharges import ensure_rules, forget_cached_rules, set_section_3b


class SurchargeRuleSerializer(serializers.ModelSerializer):
    """One rule (PER-040).

    ``kind``: ``time`` (``time_from``–``time_until``, over midnight if it ends
    earlier; ``begun_before_midnight``: only for work begun before midnight,
    and then instead of the other time-of-day rules), ``weekday`` (ISO
    ``weekdays``, 1 Monday … 7 Sunday), ``holiday``, ``date`` (``day`` and
    ``month``); the day kinds count from ``time_from`` if set. Of the day kinds
    only the highest percentage counts, of the time-of-day rules too; the two
    add up. ``code``: the kind of a rule of § 3b EStG, else empty.
    """

    id = serializers.IntegerField(required=False, help_text="Give it to change an existing rule.")
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=7), required=False, help_text="ISO weekdays."
    )

    class Meta:
        model = TimeSurchargeRule
        fields = ["id", *RULE_FIELDS, "code"]
        read_only_fields = ["position", "code"]

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """The weekdays as a list of numbers."""
        data = super().to_representation(instance)
        data["weekdays"] = [int(day) for day in instance.weekdays]
        return data


class OwnHolidaySerializer(serializers.ModelSerializer):
    """An own holiday (PER-040): ``yearly`` (``day``, ``month``), ``once`` (``date``) or ``easter`` (``easter_offset``)."""

    id = serializers.IntegerField(required=False, help_text="Give it to change an existing holiday.")

    class Meta:
        model = OwnHoliday
        fields = ["id", *HOLIDAY_FIELDS]


def _synchronised(model: Any, items: list[dict[str, Any]], prepare: Any) -> list[Any]:
    """Objects for a list sent in full: existing ones by ``id``, new ones without; all checked by the model's rules.

    Raises:
        ValidationError: The errors by the place of the item in the list.
    """
    existing = {row.pk: row for row in model.objects.all()}
    objects, errors, any_error = [], [], False
    for item in items:
        item = dict(item)
        pk = item.pop("id", None)
        if pk is not None and pk not in existing:
            errors.append({"id": [_("There is no such entry.")]})
            any_error = True
            objects.append(None)
            continue
        instance = existing[pk] if pk is not None else model()
        for name, value in prepare(item).items():
            setattr(instance, name, value)
        try:
            instance.full_clean()
        except DjangoValidationError as error:
            errors.append(error.message_dict)
            any_error = True
        else:
            errors.append({})
        objects.append(instance)
    if any_error:
        # As the REST framework names the errors of a list: by the place of the item ("rules.0.time_until").
        raise ValidationError({index: error for index, error in enumerate(errors) if error})
    return objects


def _save_list(model: Any, objects: list[Any], *, ordered: bool) -> None:
    """Delete what was left out, save the rest – each in the change log."""
    keep = {obj.pk for obj in objects if obj.pk is not None}
    for row in model.objects.exclude(pk__in=keep):
        row.delete()
    for position, obj in enumerate(objects, start=1):
        if ordered:
            obj.position = position
        obj.save()


class TimeSurchargeSettingsSerializer(CleanModelSerializer):
    """The surcharges for night, Sunday and holidays (PER-009, PER-040).

    ``on_price`` and ``on_costs``: whether crew lines planned from now on get
    the surcharges – each line keeps its own switches; no other line of a
    project ever gets them. ``german_holidays``:
    whether the statutory holidays of Germany count; ``state``: the federal
    state whose holidays count (ISO 3166-2 code without "DE-", or the variants
    ``BYE``, ``BYA``, ``SNF``, ``THF``), empty for those of the whole country.
    ``next_day_until``: for work begun before midnight, the rules of a day
    hold until this time of the next day (§ 3b EStG: 04:00); empty: not.
    ``rules`` and ``own_holidays``: sent, they replace the lists.
    """

    rules = SurchargeRuleSerializer(many=True, required=False)
    own_holidays = OwnHolidaySerializer(many=True, required=False)

    class Meta:
        model = TimeSurchargeSettings
        fields = [*SETTING_FIELDS, "rules", "own_holidays"]

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """The settings with their lists, rules in their order."""
        data = {name: value for name, value in super().to_representation(instance).items() if name in SETTING_FIELDS}
        data["rules"] = SurchargeRuleSerializer(TimeSurchargeRule.objects.order_by("position", "id"), many=True).data
        data["own_holidays"] = OwnHolidaySerializer(OwnHoliday.objects.order_by("id"), many=True).data
        return data

    def validate_rules(self, items: list[dict[str, Any]]) -> list[Any]:
        """Check every rule with the rules of the model."""

        def prepare(item: dict[str, Any]) -> dict[str, Any]:
            if "weekdays" in item:
                item["weekdays"] = "".join(sorted({str(day) for day in item["weekdays"]}))
            return item

        return _synchronised(TimeSurchargeRule, items, prepare)

    def validate_own_holidays(self, items: list[dict[str, Any]]) -> list[Any]:
        """Check every own holiday with the rules of the model."""
        return _synchronised(OwnHoliday, items, lambda item: item)

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Change the settings and, if sent, replace the lists."""
        rules = validated_data.pop("rules", None)
        holidays = validated_data.pop("own_holidays", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if rules is not None:
                _save_list(TimeSurchargeRule, rules, ordered=True)
            if holidays is not None:
                _save_list(OwnHoliday, holidays, ordered=False)
        forget_cached_rules()
        return instance


class TimeSurchargeSettingsView(ModuleAPIView):
    """``GET/PATCH /settings/surcharges`` – the surcharges for night, Sunday and holidays (PER-009, PER-040)."""

    module = Module.ADMINISTRATION
    schema_tag = "settings"

    @extend_schema(responses=TimeSurchargeSettingsSerializer)
    def get(self, request: Request) -> Response:
        """Return the settings with the rules and own holidays."""
        return Response(TimeSurchargeSettingsSerializer(ensure_rules()).data)

    @extend_schema(request=TimeSurchargeSettingsSerializer, responses=TimeSurchargeSettingsSerializer)
    def patch(self, request: Request) -> Response:
        """Change the values that were sent; everything else stays as it is."""
        serializer = TimeSurchargeSettingsSerializer(ensure_rules(), data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TimeSurchargeSettingsSerializer(TimeSurchargeSettings.load()).data)


class SectionThreeBView(ModuleAPIView):
    """``POST /settings/surcharges/section-3b`` – the rules of § 3b EStG replace the list (PER-040)."""

    module = Module.ADMINISTRATION
    schema_tag = "settings"

    @extend_schema(request=None, responses=TimeSurchargeSettingsSerializer)
    def post(self, request: Request) -> Response:
        """Set the rules of the law; the holidays and switches stay."""
        set_section_3b()
        return Response(TimeSurchargeSettingsSerializer(TimeSurchargeSettings.load()).data)


class HolidaysView(RightsViewMixin, APIView):
    """``GET /holidays`` – the holidays of a year, as Rentalars computes them (PER-009, PER-040)."""

    permission_classes = [IsAuthenticated]
    schema_tag = "settings"

    @extend_schema(
        parameters=[
            OpenApiParameter("year", int, required=False, description="Default: this year (1900 to 2200)."),
            OpenApiParameter(
                "state",
                str,
                required=False,
                description="A state as in /settings/surcharges; default: the setting (none if switched off there).",
            ),
        ],
        responses={
            200: inline_serializer(
                "Holidays",
                {
                    "year": serializers.IntegerField(),
                    "state": serializers.CharField(),
                    "state_label": serializers.CharField(),
                    "german_holidays": serializers.BooleanField(),
                    "holidays": inline_serializer(
                        "Holiday",
                        {
                            "date": serializers.DateField(),
                            "key": serializers.CharField(help_text='"own" for an own holiday.'),
                            "name": serializers.CharField(),
                            "own": serializers.BooleanField(),
                        },
                        many=True,
                    ),
                },
            )
        },
    )
    def get(self, request: Request) -> Response:
        """The holidays in the order of the days."""
        raw_year = request.query_params.get("year", "")
        try:
            year = int(raw_year) if raw_year else timezone.localdate().year
        except ValueError:
            year = 0
        if not 1900 <= year <= 2200:
            raise ValidationError({"year": _("Give a year from 1900 to 2200.")})
        settings = TimeSurchargeSettings.load()
        state = request.query_params.get("state")
        german = True
        if state is None:
            state, german = settings.state, settings.german_holidays
        if state not in STATES:
            raise ValidationError(
                {"state": _("Unknown federal state. Known: %(states)s") % {"states": ", ".join(sorted(STATES - {""}))}}
            )
        keys = holidays_of(year, state) if german else {}
        own = tuple(holiday.spec() for holiday in OwnHoliday.objects.order_by("id"))
        days = calendar_of(year, state, german, own)
        listed = []
        for day in sorted(days):
            for name, is_own in days[day]:
                listed.append({"date": day, "key": "own" if is_own else keys[day], "name": str(name), "own": is_own})
        return Response(
            {
                "year": year,
                "state": state,
                "state_label": state_label(state),
                "german_holidays": german,
                "holidays": listed,
            }
        )
