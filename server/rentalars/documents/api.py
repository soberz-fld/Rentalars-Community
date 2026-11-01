# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the documents (DOK-003 to DOK-008, DOK-010).

PRJ-045, PRJ-046: offer, order confirmation and invoice of a whole project
contain all its parts that are not cancelled; on a part they are refused
with a message that names the whole project.

DOK-013: an offer is made with every position or with its groups only, and
holds until a date or for a number of days. PRJ-081: the deployment view of
a project as PDF, for the caller.

DOK-014: while the setting "use Rentalars as accounting software" is off (``/settings``,
``system.invoices_enabled``), invoices and cancellations are refused with 400;
the documents made before can still be read.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight
from rentalars.api.permissions import ModulePermission
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, ModuleViewSet, RightsViewMixin
from rentalars.documents import services, template_texts
from rentalars.documents.models import (
    MAX_VALIDITY_DAYS,
    PRICED_KINDS,
    BillingType,
    Document,
    DocumentDetail,
    DocumentKind,
    DocumentTemplate,
    TextBlock,
    text_block_kinds,
)
from rentalars.projects.access import ProjectAccess, project_for


class DocumentSerializer(serializers.ModelSerializer):
    """A stored document; the PDF and the XRechnung are fetched from their addresses.

    DOK-013: ``detail`` says whether an offer shows every position (``lines``)
    or only its groups (``groups``); ``validity_days`` how many days after its
    date it holds.

    ``project`` is ``null`` for a document made in Accounting without a
    project (``/accounting/documents/drafts``); ``customer`` names the customer
    of every document, ``reference`` is the subject line of a free document and
    ``print_product_descriptions`` says whether the description of the products
    was printed under the positions.
    """

    pdf_url = serializers.SerializerMethodField()
    xml_url = serializers.SerializerMethodField()
    validity_days = serializers.IntegerField(
        read_only=True, allow_null=True, help_text="Offers: days from the date until valid_until; else null."
    )
    billed_projects = serializers.PrimaryKeyRelatedField(
        many=True,
        read_only=True,
        help_text="DOK-016: the service cases a monthly invoice bills – `project` is the first of them; "
        "empty for the invoice of one project.",
    )

    class Meta:
        model = Document
        fields = [
            "id",
            "project",
            "customer",
            "reference",
            "print_product_descriptions",
            "kind",
            "number",
            "title",
            "issued_on",
            "created_at",
            "net_total",
            "gross_total",
            "due_on",
            "valid_until",
            "validity_days",
            "detail",
            "sha256",
            "cancels",
            "cancelled_by",
            "billing_type",
            "billing_number",
            "credit_for",
            "sent_at",
            "sent_to",
            "pdf_url",
            "xml_url",
            "billed_projects",
        ]
        read_only_fields = fields

    def get_pdf_url(self, document: Document) -> str:
        """Where the PDF is fetched."""
        return f"/api/v1/documents/{document.pk}/pdf"

    def get_xml_url(self, document: Document) -> str:
        """Where the XRechnung is fetched; empty for other kinds."""
        return f"/api/v1/documents/{document.pk}/xml" if document.xml_file else ""


#: The kinds that can be asked for; a cancellation is made from its invoice.
MAKEABLE_KINDS = [(kind.value, kind.label) for kind in DocumentKind if kind != DocumentKind.CANCELLATION]


class DocumentRequestSerializer(serializers.Serializer):
    """What to make (DOK-003 to DOK-006, DOK-010, DOK-013)."""

    kind = serializers.ChoiceField(choices=MAKEABLE_KINDS)
    text_blocks = serializers.ListField(child=serializers.IntegerField(), required=False)
    packlist = serializers.IntegerField(required=False, allow_null=True)
    valid_until = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Offers only: until when the offer holds (DOK-010). Without it and without validity_days: "
        "the validity in days of the offer's template, 14 unless changed (DOK-013).",
    )
    validity_days = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        max_value=MAX_VALIDITY_DAYS,
        help_text="Offers only: how many days after its date the offer holds (DOK-013). Given together with "
        "valid_until, both must name the same day.",
    )
    detail = serializers.ChoiceField(
        choices=DocumentDetail.choices,
        required=False,
        help_text="Offers only: 'lines' – every position (default); 'groups' – every group with its description "
        "and sum, without the positions in it (DOK-013). The totals are the same.",
    )
    print_product_descriptions = serializers.BooleanField(
        required=False,
        allow_null=True,
        help_text="Print the description of each product under its position. Left out or null: as the "
        "template of the kind says (/document-templates). Stored with the document.",
    )
    billing_type = serializers.ChoiceField(
        choices=[(BillingType.ADVANCE, "advance"), (BillingType.PARTIAL, "partial"), (BillingType.FINAL, "final")],
        required=False,
        allow_blank=True,
        help_text="Invoices only: 'advance' (Abschlagsrechnung) or 'partial' (Teilrechnung) bill the "
        "`amount` or `percent`; 'final' (Schlussrechnung) bills the whole project and deducts the advance and "
        "partial invoices. Left out or empty: the ordinary invoice of the whole project. Refused (400) as long as "
        "advance or partial invoices are valid and the type is empty, and when more would be billed than the "
        "project amounts to.",
    )
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="The net amount of an advance or partial invoice (not together with `percent`).",
    )
    percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="The net amount of an advance or partial invoice as a percentage of the net total of "
        "the project (above 0, at most 100; not together with `amount`).",
    )
    note = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        help_text="What an advance or partial invoice is for; stands on the invoice.",
    )


def _priced_allowed(view: Any, kind: str) -> None:
    if kind in PRICED_KINDS and not view.rights.has(SpecialRight.PRICES):
        raise PermissionDenied


def _options(project: Any, data: dict[str, Any]) -> dict[str, Any]:
    from rentalars.packing.models import Packlist

    packlist = data.get("packlist")
    options = {
        "text_block_ids": data.get("text_blocks") or [],
        "packlist": get_object_or_404(Packlist, pk=packlist, project=project) if packlist else None,
    }
    if data.get("kind") == DocumentKind.OFFER:
        options["valid_until"] = data.get("valid_until")
        options["validity_days"] = data.get("validity_days")
    # DOK-013: a level of detail for another kind than an offer is refused by the service, not ignored.
    options["detail"] = data.get("detail")
    options["print_product_descriptions"] = data.get("print_product_descriptions")
    if data.get("kind") == DocumentKind.INVOICE and data.get("billing_type"):
        from rentalars.documents.billing import Billing

        options["billing"] = Billing(
            type=data["billing_type"],
            amount=data.get("amount"),
            percent=data.get("percent"),
            note=data.get("note") or "",
        )
    return options


class ProjectDocumentsView(ModuleAPIView):
    """``/projects/{id}/documents`` – the documents of a project; ``POST`` makes one (DOK-007)."""

    module = Module.PROJECTS

    @extend_schema(responses=DocumentSerializer(many=True))
    def get(self, request: Request, project_pk: int) -> Response:
        """The documents, newest first; priced ones only with the price right."""
        project = project_for(request, project_pk, ProjectAccess.READ)
        prices = self.rights.has(SpecialRight.PRICES)
        # DOK-016: with a service case also the monthly invoice that bills it.
        listed = Document.objects.filter(
            Q(project=project) | Q(billed_projects=project) | Q(cancels__billed_projects=project)
        ).distinct()
        documents = [
            document
            for document in listed
            if (prices or not document.is_priced)
            and services.may_open_billed(document, rights=self.rights, user=request.user)
        ]
        return Response(DocumentSerializer(documents, many=True).data)

    @extend_schema(request=DocumentRequestSerializer, responses={201: DocumentSerializer})
    def post(self, request: Request, project_pk: int) -> Response:
        """Make a document; it gets the next number and is never changed afterwards.

        DOK-014: an invoice is refused (400) while "use Rentalars as accounting software" is off.
        """
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        serializer = DocumentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kind = serializer.validated_data["kind"]
        _priced_allowed(self, kind)
        # PRJ-045, PRJ-049: refused on a part, and to whoever may not read every part of a whole project.
        document = services.create_document(
            project, kind, user=request.user, rights=self.rights, **_options(project, serializer.validated_data)
        )
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class ProjectDocumentPreviewView(ModuleAPIView):
    """``POST /projects/{id}/documents/preview`` – the PDF as it would come out, nothing stored."""

    module = Module.PROJECTS

    @extend_schema(request=DocumentRequestSerializer, responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def post(self, request: Request, project_pk: int) -> HttpResponse:
        """A draft PDF without number; for an invoice 400 while invoices are switched off (DOK-014)."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        serializer = DocumentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kind = serializer.validated_data["kind"]
        _priced_allowed(self, kind)
        pdf = services.preview(
            project, kind, rights=self.rights, user=request.user, **_options(project, serializer.validated_data)
        )
        return HttpResponse(pdf, content_type="application/pdf")


class DeploymentPdfView(ModuleAPIView):
    """``GET /projects/{id}/deployment/pdf`` – the deployment view as PDF "Einsatzübersicht" (PRJ-081).

    The same as ``/projects/{id}/deployment`` for the caller (AUT-025): what
    crew and freelancers may see, planners with every contact; never a
    price, a rate or the customer (AUT-023). Not stored, no number.
    """

    module = Module.PROJECTS

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request: Request, project_pk: int) -> HttpResponse:
        """The PDF, made now."""
        from rentalars.documents.deployment import deployment_pdf, file_name
        from rentalars.projects.models import Project

        project = project_for(
            request,
            project_pk,
            ProjectAccess.DEPLOYMENT,
            queryset=Project.objects.select_related("contact", "manager", "venue_site", "parent"),
        )
        response = HttpResponse(deployment_pdf(project, rights=self.rights, user=request.user), "application/pdf")
        response["Content-Disposition"] = f'inline; filename="{file_name(project)}"'
        return response


class _DocumentView(ModuleAPIView):
    module = Module.PROJECTS

    def document(self, request: Request, pk: int, minimum: ProjectAccess = ProjectAccess.READ) -> Document:
        document = get_object_or_404(Document, pk=pk)
        if document.project_id is None:
            # Free outgoing documents: no project to open – the rights of Buchhaltung → Ausgangsbelege.
            from rentalars.documents import free

            if not (free.may_change(self.rights) if minimum >= ProjectAccess.EDIT else free.may_see(self.rights)):
                raise PermissionDenied
        else:
            project_for(request, document.project_id, minimum)
        if document.is_priced and not self.rights.has(SpecialRight.PRICES):
            raise PermissionDenied
        # DOK-016: a monthly invoice needs the same access to every case it bills.
        if not services.may_open_billed(document, rights=self.rights, user=request.user, minimum=minimum):
            raise PermissionDenied
        return document


class DocumentDetailView(_DocumentView):
    """``/documents/{id}``."""

    @extend_schema(responses=DocumentSerializer)
    def get(self, request: Request, pk: int) -> Response:
        """One document."""
        return Response(DocumentSerializer(self.document(request, pk)).data)


class DocumentPdfView(_DocumentView):
    """``/documents/{id}/pdf`` – the stored PDF (DOK-007)."""

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request: Request, pk: int) -> Any:
        """The file."""
        from rentalars.core.uploads import document_response

        document = self.document(request, pk)
        return document_response(document.file.name, document.file_name)


class DocumentXmlView(_DocumentView):
    """``/documents/{id}/xml`` – the XRechnung of an invoice or cancellation (DOK-006)."""

    @extend_schema(responses={(200, "application/xml"): OpenApiTypes.BINARY})
    def get(self, request: Request, pk: int) -> Any:
        """The UBL file."""
        from rentalars.core.uploads import protected_file_response

        document = self.document(request, pk)
        if not document.xml_file:
            raise Http404
        return protected_file_response(document.xml_file.name, download_name=f"{document.number}.xml")


class DocumentCancelView(_DocumentView):
    """``POST /documents/{id}/cancel`` – cancel an invoice by a cancellation (DOK-006)."""

    @extend_schema(request=None, responses={201: DocumentSerializer})
    def post(self, request: Request, pk: int) -> Response:
        """Make the cancellation; both stay with the project. 400 while invoices are switched off (DOK-014)."""
        invoice = self.document(request, pk, ProjectAccess.EDIT)
        cancellation = services.cancel_invoice(invoice, user=request.user)
        return Response(DocumentSerializer(cancellation).data, status=status.HTTP_201_CREATED)


class DocumentCreditRequestSerializer(serializers.Serializer):
    """How much of an invoice is credited."""

    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, help_text="The net amount credited …"
    )
    percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="… or a percentage of what the invoice still bills (net) – one of the two.",
    )
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, help_text="What it is for.")


class DocumentCreditView(_DocumentView):
    """``POST /documents/{id}/credit`` – credit a part of an invoice by a partial credit note (DOK-035)."""

    @extend_schema(request=DocumentCreditRequestSerializer, responses={201: DocumentSerializer})
    def post(self, request: Request, pk: int) -> Response:
        """Make the credit note (negative amounts, own number); the invoice stays valid, 400 if more than is left."""
        from rentalars.documents import billing

        invoice = self.document(request, pk, ProjectAccess.EDIT)
        serializer = DocumentCreditRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        credit = billing.credit_invoice(
            invoice,
            amount=data.get("amount"),
            percent=data.get("percent"),
            note=data.get("note", ""),
            user=request.user,
        )
        return Response(DocumentSerializer(credit).data, status=status.HTTP_201_CREATED)


class DocumentTemplateSerializer(CleanModelSerializer):
    """Heading and texts of a kind of document (DOK-005).

    ``validity_days``: the offer only – how many days a new offer is valid
    (DOK-013); ``null`` for the other kinds.

    ``print_product_descriptions`` – new documents of the kind print the
    description of the products under their positions (it can be chosen again
    for each document); ``free_introduction`` – the introduction of a document
    made in Accounting without a project, empty: a standard text.
    """

    class Meta:
        model = DocumentTemplate
        fields = [
            "id",
            "kind",
            "title",
            "introduction",
            "closing",
            "footer",
            "show_logo",
            "validity_days",
            "print_product_descriptions",
            "free_introduction",
        ]
        read_only_fields = ["kind"]


class TemplateDefaultsQuerySerializer(serializers.Serializer):
    """``GET /document-templates/defaults``: the language to compare with (DOK-018)."""

    language = serializers.ChoiceField(choices=list(template_texts.LANGUAGES))


class TemplateDefaultsRequestSerializer(serializers.Serializer):
    """``POST /document-templates/defaults``: which default texts to take over (DOK-018)."""

    language = serializers.ChoiceField(choices=list(template_texts.LANGUAGES))
    kinds = serializers.ListField(
        child=serializers.ChoiceField(choices=DocumentKind.choices),
        required=False,
        help_text="The kinds of document; left out or empty: all.",
    )
    include_own = serializers.BooleanField(
        required=False, default=False, help_text="Replace own texts too – those that are no default text."
    )
    document_language = serializers.BooleanField(
        required=False, default=False, help_text="Switch the language of the documents to the language as well."
    )


class TemplateDefaultsSerializer(serializers.Serializer):
    """The comparison with the default texts of a language (DOK-018); after ``POST`` with what changed."""

    language = serializers.CharField()
    document_language = serializers.CharField(help_text="The language of the documents (company data).")
    templates = serializers.ListField(
        child=serializers.DictField(),
        help_text="Every kind: {kind, changes: [{field, current, new, own}]} – the fields the default texts change.",
    )
    changed = serializers.ListField(child=serializers.DictField(), required=False, help_text="POST: [{kind, field}]")
    kept_own = serializers.ListField(child=serializers.DictField(), required=False, help_text="POST: [{kind, field}]")
    document_language_changed = serializers.BooleanField(required=False)


class DocumentTemplateViewSet(
    RightsViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """``/document-templates`` – one per kind; they are changed, not added or deleted (DOK-005).

    DOK-018: ``/document-templates/defaults`` compares them with the
    default texts of a language and takes those over (:meth:`defaults`).
    """

    module = Module.ADMINISTRATION
    read_for_all = True
    permission_classes: ClassVar[list[Any]] = [ModulePermission]
    serializer_class = DocumentTemplateSerializer
    pagination_class = None

    def get_queryset(self) -> Any:
        """Every kind, its template created with the start texts if missing."""
        if getattr(self, "swagger_fake_view", False):  # building the API description: no database needed
            return DocumentTemplate.objects.none()
        for kind in DocumentKind.values:
            services.template_for(kind)
        return DocumentTemplate.objects.order_by("kind")

    @extend_schema(
        methods=["GET"],
        parameters=[OpenApiParameter("language", str, enum=list(template_texts.LANGUAGES), required=True)],
        responses={200: TemplateDefaultsSerializer},
    )
    @extend_schema(
        methods=["POST"], request=TemplateDefaultsRequestSerializer, responses={200: TemplateDefaultsSerializer}
    )
    @action(detail=False, methods=["get", "post"], url_path="defaults")
    def defaults(self, request: Request) -> Response:
        """The default texts of a language for heading, introduction and closing text (DOK-018).

        ``GET ?language=en`` changes nothing: ``templates`` lists every kind
        with the fields the default texts would change – ``current``, ``new``
        and ``own`` (neither the German nor the English default text) – and
        ``document_language`` the language of the documents now. It needs read
        access to the settings.

        ``POST {"language", "kinds", "include_own", "document_language"}``
        takes them over – for the ``kinds`` named (all if left out), own
        texts only with ``include_own: true``; ``document_language: true``
        switches the language of the documents as well. Footer, logo and
        validity stay. The answer is the comparison as it is afterwards, with
        ``changed`` (``[{"kind", "field"}]``), ``kept_own`` and
        ``document_language_changed``. It needs write access to the settings.
        """
        from rentalars.core.i18n import document_language

        if request.method == "GET":
            if not self.rights.can_read(Module.ADMINISTRATION):
                raise PermissionDenied
            serializer = TemplateDefaultsQuerySerializer(data=request.query_params)
            serializer.is_valid(raise_exception=True)
            language = serializer.validated_data["language"]
            return Response(_defaults_document(language, document_language()))
        serializer = TemplateDefaultsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = template_texts.take_over(
            data["language"],
            kinds=data.get("kinds") or None,
            include_own=data.get("include_own", False),
            document_language=data.get("document_language", False),
        )
        document = _defaults_document(data["language"], document_language())
        document.update(
            changed=[{"kind": change.kind, "field": change.name} for change in result.changed],
            kept_own=[{"kind": change.kind, "field": change.name} for change in result.kept_own],
            document_language_changed=result.document_language_changed,
        )
        return Response(document)


def _defaults_document(language: str, document_language: str) -> dict[str, Any]:
    """The comparison with the default texts of ``language`` as JSON (DOK-018)."""
    return {
        "language": language,
        "document_language": document_language,
        "templates": [
            {
                "kind": comparison.kind,
                "changes": [change.document() for change in comparison.changes],
            }
            for comparison in template_texts.compare(language)
        ],
    }


class TextBlockSerializer(CleanModelSerializer):
    """A paragraph to add to documents (DOK-005)."""

    kinds = serializers.ListField(child=serializers.ChoiceField(choices=text_block_kinds()), required=False)

    class Meta:
        model = TextBlock
        fields = ["id", "name", "text", "kinds", "is_active"]


class TextBlockViewSet(ModuleViewSet):
    """``/text-blocks`` – paragraphs to add when a document is made (DOK-005)."""

    module = Module.ADMINISTRATION
    read_for_all = True
    queryset = TextBlock.objects.order_by("name")
    serializer_class = TextBlockSerializer
    pagination_class = None
