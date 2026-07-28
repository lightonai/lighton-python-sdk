# Generated from the LightOn OpenAPI schema. Do not edit by hand — run 'make gen-types'.

from __future__ import annotations

from typing import Annotated, Any
from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field, RootModel
from enum import Enum, StrEnum
from uuid import UUID


class APIV3BatchErrorResponse(BaseModel):
    id: Annotated[
        str | None,
        Field(
            description="Job/resource id when one already exists (useful for async error diagnosis); null otherwise."
        ),
    ]
    code: Annotated[int, Field(description="HTTP status code")]
    error: Annotated[
        str, Field(description="Error code used by the UI as a translation key")
    ]
    detail: Annotated[
        str, Field(description="Human-readable error message for developers")
    ]
    doc_url: Annotated[
        str, Field(description="Link to the error-code documentation page")
    ]
    index: Annotated[
        int | None,
        Field(description="0-based position of the failing action in the batch."),
    ] = None


class APIV3ErrorResponse(BaseModel):
    id: Annotated[
        str | None,
        Field(
            description="Job/resource id when one already exists (useful for async error diagnosis); null otherwise."
        ),
    ]
    code: Annotated[int, Field(description="HTTP status code")]
    error: Annotated[
        str, Field(description="Error code used by the UI as a translation key")
    ]
    detail: Annotated[
        str, Field(description="Human-readable error message for developers")
    ]
    doc_url: Annotated[
        str, Field(description="Link to the error-code documentation page")
    ]


class APIV3FieldError(BaseModel):
    error: Annotated[str, Field(description="Error code / translation key")]
    detail: Annotated[
        str, Field(description="Human-readable description of the field error")
    ]


class APIV3ValidationErrorResponse(BaseModel):
    id: Annotated[
        str | None,
        Field(
            description="Job/resource id when one already exists (useful for async error diagnosis); null otherwise."
        ),
    ]
    code: Annotated[int, Field(description="HTTP status code")]
    error: Annotated[
        str, Field(description="Error code used by the UI as a translation key")
    ]
    detail: Annotated[
        str, Field(description="Human-readable error message for developers")
    ]
    doc_url: Annotated[
        str, Field(description="Link to the error-code documentation page")
    ]
    fields: Annotated[
        dict[str, list[APIV3FieldError]] | None,
        Field(description="Field-level validation errors keyed by field name"),
    ] = None


class AttributeDefResponse(BaseModel):
    name: Annotated[str, Field(title="Name")]
    label: Annotated[str, Field(title="Label")]
    type: Annotated[str, Field(title="Type")]
    required: Annotated[bool, Field(title="Required")]
    description: Annotated[str | None, Field(title="Description")] = ""
    choices: Annotated[list[str] | None, Field(title="Choices")] = []


class AttributeSchema(BaseModel):
    name: Annotated[
        str, Field(description="Attribute identifier in snake_case.", title="Name")
    ]
    label: Annotated[
        str | None, Field(description="Human-readable attribute label.", title="Label")
    ] = ""
    value: Annotated[
        str | int | float | bool | list[str] | None,
        Field(
            description="Current attribute value. Shape depends on type: string, number, boolean, date string, or array of strings for multi-select. Null when unset.",
            title="Value",
        ),
    ]
    type: Annotated[
        str,
        Field(
            description="Public attribute type, e.g. text, number, date, boolean, select, multi-select.",
            title="Type",
        ),
    ]
    required: Annotated[
        bool,
        Field(
            description="Whether the attribute is required by the schema.",
            title="Required",
        ),
    ]
    description: Annotated[
        str | None,
        Field(
            description="Optional descriptive text from the schema.",
            title="Description",
        ),
    ] = ""
    choices: Annotated[
        list[str] | None,
        Field(
            description="Allowed values for select and multi-select attributes.",
            title="Choices",
        ),
    ] = []


class AttributeValueResponse(BaseModel):
    name: Annotated[str, Field(title="Name")]
    value: Annotated[
        str | int | float | bool | list[str] | None,
        Field(
            description="Attribute value. Shape depends on type: string, number, boolean, date string, or array of strings for multi-select.",
            title="Value",
        ),
    ]
    content_type_path: Annotated[str, Field(title="Content Type Path")]


class BatchResultItem(BaseModel):
    status: Annotated[int, Field(title="Status")]
    data: Annotated[dict[str, Any] | None, Field(title="Data")] = None


class BlankEnum(Enum):
    field_ = ""


class BudgetAlertResponse(BaseModel):
    model_config = ConfigDict(
        regex_engine="python-re",
    )
    id: Annotated[int, Field(title="Id")]
    is_enabled: Annotated[bool, Field(title="Is Enabled")]
    threshold_type: Annotated[str, Field(title="Threshold Type")]
    threshold_value: Annotated[
        str, Field(pattern="^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$", title="Threshold Value")
    ]


class BudgetResponse(BaseModel):
    model_config = ConfigDict(
        regex_engine="python-re",
    )
    is_enabled: Annotated[
        bool,
        Field(
            description="Whether this budget is actively enforced.", title="Is Enabled"
        ),
    ]
    amount_eur: Annotated[
        str,
        Field(
            description="Monthly budget cap in EUR.",
            pattern="^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
            title="Amount Eur",
        ),
    ]
    currency: Annotated[
        str | None, Field(description="ISO 4217 currency code.", title="Currency")
    ] = "EUR"
    current_cycle_start: Annotated[
        str,
        Field(
            description="First day of the current billing cycle (ISO date).",
            title="Current Cycle Start",
        ),
    ]
    next_cycle_start: Annotated[
        str,
        Field(
            description="First day of the next billing cycle (ISO date).",
            title="Next Cycle Start",
        ),
    ]
    monthly_spend_eur: Annotated[
        str,
        Field(
            description="Current month's spend in EUR.",
            pattern="^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
            title="Monthly Spend Eur",
        ),
    ]
    available_eur: Annotated[
        str,
        Field(
            description="Remaining budget for the current cycle in EUR.",
            pattern="^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
            title="Available Eur",
        ),
    ]
    alerts: Annotated[
        list[BudgetAlertResponse] | None,
        Field(description="Alert thresholds.", title="Alerts"),
    ] = None


class CommonErrorResponse(BaseModel):
    error: str


class ContentTypeActionRequestActionEnum(StrEnum):
    adopt = "adopt"
    define_content_type = "define_content_type"
    undefine_content_type = "undefine_content_type"
    define_attribute = "define_attribute"
    undefine_attribute = "undefine_attribute"


class ContentTypeAssignmentResponse(BaseModel):
    content_type_path: Annotated[str, Field(title="Content Type Path")]
    label: Annotated[str, Field(title="Label")]


class ContentTypeAttributesResponse(BaseModel):
    path: Annotated[
        str,
        Field(description="Canonical colon-separated content type path.", title="Path"),
    ]
    code: Annotated[
        str,
        Field(description="Leaf node code (last segment of the path).", title="Code"),
    ]
    label: Annotated[
        str, Field(description="Leaf label for the content type path.", title="Label")
    ]
    labels: Annotated[list[str] | None, Field(title="Labels")] = []
    attributes: Annotated[list[AttributeSchema], Field(title="Attributes")]


class ContentTypeNodeResponse(BaseModel):
    path: Annotated[str, Field(title="Path")]
    code: Annotated[str, Field(title="Code")]
    label: Annotated[str, Field(title="Label")]
    description: Annotated[str | None, Field(title="Description")] = ""
    source: Annotated[str, Field(title="Source")]
    inherit_attributes: Annotated[bool | None, Field(title="Inherit Attributes")] = True
    attributes: Annotated[
        list[AttributeDefResponse] | None,
        Field(title="Attributes", validate_default=True),
    ] = []
    children: Annotated[
        list[ContentTypeNodeResponse] | None,
        Field(title="Children", validate_default=True),
    ] = []


class ContentTypeWrite201Response(
    RootModel[ContentTypeNodeResponse | AttributeDefResponse]
):
    root: ContentTypeNodeResponse | AttributeDefResponse


class ContentTypesListResponse(BaseModel):
    content_types: Annotated[
        list[ContentTypeNodeResponse], Field(title="Content Types")
    ]
    can_edit: Annotated[bool | None, Field(title="Can Edit")] = None


class CreatedBy(BaseModel):
    """
    Shallow user object for the file creator.
    """

    id: Annotated[int, Field(description="User ID")]
    first_name: Annotated[str, Field(description="First name")]
    last_name: Annotated[str, Field(description="Last name")]
    username: Annotated[str, Field(description="Username")]


class DocumentAttributesListResponse(BaseModel):
    content_types: Annotated[
        list[ContentTypeAttributesResponse], Field(title="Content Types")
    ]
    can_edit: Annotated[bool, Field(title="Can Edit")]
    unlinked: Annotated[
        list[AttributeSchema] | None, Field(title="Unlinked", validate_default=True)
    ] = []


class DocumentFacetAttributeValueSchema(BaseModel):
    """
    OpenAPI schema for a compact attribute value entry.
    """

    value: Annotated[
        Any, Field(description="Attribute value (type depends on attribute definition)")
    ]
    type: Annotated[
        str,
        Field(
            description="Attribute type (text, number, date, boolean, select, multi_select)"
        ),
    ]
    label: Annotated[
        str | None,
        Field(
            description="User-readable attribute label (present when include_details=true)"
        ),
    ] = None


class DocumentFacetCompactSchema(BaseModel):
    """
    OpenAPI schema for compact content type response (Tier 1 — list default).
    """

    path: Annotated[
        str,
        Field(
            description="Colon-separated content type path (e.g. legal:contract:nda)"
        ),
    ]
    label: Annotated[str, Field(description="User-readable label (leaf node)")]
    attribute_values: Annotated[
        dict[str, DocumentFacetAttributeValueSchema] | None,
        Field(
            description="Map of attribute name to {value, type}. Only present when include_details=true."
        ),
    ] = None


class ExternalMetadataRequest(BaseModel):
    """
    Validates external document metadata for V3 file endpoints.

    All fields are optional to support both creation (where doc_id is typically
    required - validated at the view level) and partial updates (all optional).
    """

    external_id: Annotated[
        str | None,
        Field(
            description="External document ID in the source system. Required when creating external metadata for the first time."
        ),
    ] = None
    doc_type: Annotated[
        str | None,
        Field(description="External document type (e.g. 'incident', 'page')"),
    ] = None
    additional_metadata: Annotated[
        Any | None,
        Field(
            description="Arbitrary JSON object with extra information about the document (e.g. URL, version, timestamps). Passed through as-is."
        ),
    ] = None


class ExternalMetadataResponse(BaseModel):
    external_id: Annotated[str, Field(description="External document ID")]
    doc_type: Annotated[str, Field(description="External document type")]
    additional_metadata: Annotated[
        Any, Field(description="Additional metadata associated with the document")
    ]


class ExtractDocument(BaseModel):
    filename: Annotated[str | None, Field(title="Filename")] = None
    page_count: Annotated[int | None, Field(title="Page Count")] = None
    file_size_bytes: Annotated[int | None, Field(title="File Size Bytes")] = None
    mime_type: Annotated[str | None, Field(title="Mime Type")] = None


class ExtractPagination(BaseModel):
    page: Annotated[int, Field(title="Page")]
    page_size: Annotated[int, Field(title="Page Size")]
    total_items: Annotated[int, Field(title="Total Items")]
    total_pages: Annotated[int, Field(title="Total Pages")]
    has_next: Annotated[bool, Field(title="Has Next")]
    has_prev: Annotated[bool, Field(title="Has Prev")]


class ExtractRequest(BaseModel):
    """
    Body for POST /api/v3/extract.

    ``schema`` is the JSON Schema that drives extraction. It arrives as a dict
    on JSON requests and as a JSON-encoded string on multipart requests — both
    are coerced to ``dict``.

    ``options`` is a free-form dict; currently supports ``{"async": bool}``.
    """

    document: Annotated[str | None, Field(title="Document")] = None
    schema_: Annotated[dict[str, Any], Field(alias="schema", title="Schema")]
    options: Annotated[dict[str, Any] | None, Field(title="Options")] = None


class ExtractResult(BaseModel):
    data: Annotated[list[dict[str, Any]] | None, Field(title="Data")] = None
    pagination: ExtractPagination | None = None


class ExtractUsage(BaseModel):
    pages_processed: Annotated[int | None, Field(title="Pages Processed")] = None


class Id(RootModel[int]):
    root: Annotated[int, Field(ge=1)]


class FileBulkDeleteRequestSerializerV3(BaseModel):
    """
    Request serializer for V3 bulk file deletion.
    """

    ids: list[Id]


class FileCreateRequestSerializerV3(BaseModel):
    """
    Request serializer for POST /api/v3/files endpoint.

    Phase 1 Implementation - Core Parameters:
    - file: The file to upload (required)
    - name: Custom filename (optional, defaults to uploaded filename)
    - title: Custom title for the document (optional)
    - workspace_id: Workspace ID where the document will be stored (required)
    - parser: Deprecated — ignored, the platform always uses its default pipeline
    """

    file: Annotated[AnyUrl, Field(description="The file to upload (binary data)")]
    filename: Annotated[
        str | None,
        Field(
            description="Custom filename (defaults to uploaded filename if not provided)",
            max_length=255,
        ),
    ] = None
    title: Annotated[
        str | None,
        Field(
            description="Custom title for the document. If not provided, defaults to filename without extension.",
            max_length=255,
        ),
    ] = None
    workspace_id: Annotated[
        int, Field(description="Workspace where the document will be stored.")
    ]
    parser: Annotated[
        str | None,
        Field(
            deprecated=True,
            description="Deprecated — the platform always uses its default ingestion pipeline. This field is accepted but ignored. Will be removed in a future release.",
            max_length=255,
        ),
    ] = None
    tags: Annotated[
        list[int] | None,
        Field(description="List of tag IDs to assign to the document on creation."),
    ] = None
    external_metadata: Annotated[
        ExternalMetadataRequest | None,
        Field(
            description="External source metadata for documents ingested from third-party systems. Provide as a JSON object with `external_id` (required), `doc_type` (optional), and `additional_metadata` (optional JSON object)."
        ),
    ] = None


class FileFacetActionRequestActionEnum(StrEnum):
    classify = "classify"
    unclassify = "unclassify"
    set_value = "set_value"
    clear_value = "clear_value"


class FileFacetWriteResponse(
    RootModel[AttributeValueResponse | ContentTypeAssignmentResponse]
):
    root: AttributeValueResponse | ContentTypeAssignmentResponse


class FileTaggingAddRequest(BaseModel):
    """
    Request serializer for adding tags to a file.
    """

    tags: Annotated[
        list[int], Field(description="List of tag IDs to add to the file", min_length=1)
    ]


class JobProgress(BaseModel):
    """
    Live progress of a long-running async job while it is in flight.

    Shared by the parse (``GET /api/v3/parse/<id>``) and extract
    (``GET /api/v3/extract/<id>``) polling envelopes: ``pages_processed`` is the
    count of pages done so far and ``percentage`` is the completion percentage
    [0, 100] derived from it.
    """

    percentage: Annotated[int, Field(title="Percentage")]
    pages_processed: Annotated[int, Field(title="Pages Processed")]


class KindEnum(StrEnum):
    """
    * `library` - library
    * `folder` - folder
    """

    library = "library"
    folder = "folder"


class LanguageEnum(StrEnum):
    """
    * `en` - English
    * `fr` - French
    * `es` - Spanish
    * `it` - Italian
    * `ar` - Arabic
    * `nl` - Dutch
    * `sv` - Swedish
    * `de` - German
    * `ja` - Japanese
    * `zh` - Chinese
    * `ko` - Korean
    """

    en = "en"
    fr = "fr"
    es = "es"
    it = "it"
    ar = "ar"
    nl = "nl"
    sv = "sv"
    de = "de"
    ja = "ja"
    zh = "zh"
    ko = "ko"


class ModeEnum(StrEnum):
    """
    * `text` - text
    * `vision` - vision
    """

    text = "text"
    vision = "vision"


class Page(BaseModel):
    """
    Canonical per-page document text object.

    Originates with /parse and is reused by /ocr and /files (the latter imports it
    from here) so a client can switch between live parsing and reading an
    already-ingested file without reshaping page data. Defined once and reused
    everywhere — never redefine this shape per app.

    Extensible: future per-page fields (tables, images, confidence, ...) can be
    added here without breaking callers that only consume ``index`` + ``markdown``.
    """

    index: Annotated[
        int, Field(description="Page number within the document (1-based).")
    ]
    markdown: Annotated[str, Field(description="Page text rendered as Markdown.")]


class ParseAsyncResponse(BaseModel):
    """
    Returned by ``POST /api/v3/parse`` with ``options.async=true`` — caller polls ``GET /api/v3/parse/<id>``.
    """

    id: Annotated[
        str,
        Field(
            description="Parse job id (e.g. `parse_Kg`); poll via GET /api/v3/parse/<id>."
        ),
    ]
    status: Annotated[str, Field(description="Initial status — typically 'pending'.")]
    created_at: Annotated[
        AwareDatetime, Field(description="When the job was accepted.")
    ]


class ParseDocument(BaseModel):
    filename: str
    page_count: int | None
    file_size_bytes: int
    mime_type: str


class ParseError(BaseModel):
    """
    Failure details surfaced on terminal-failed async parse jobs.
    """

    message: str


class Options(BaseModel):
    """
    Parse options. Currently supports `{"async": true}` to queue the document.
    """

    model_config = ConfigDict(
        extra="allow",
    )
    async_: Annotated[
        bool | None,
        Field(
            alias="async",
            description="Queue the document for asynchronous parsing and return 202 with a job id.",
        ),
    ] = False


class ParseJsonRequest(BaseModel):
    document: Annotated[
        AnyUrl, Field(description="Publicly accessible URL of the document to parse.")
    ]
    options: Annotated[
        Options | None,
        Field(
            description='Parse options. Currently supports `{"async": true}` to queue the document.'
        ),
    ] = None


class Options1(BaseModel):
    """
    Parse options as a JSON-encoded string. Currently supports `{"async": true}` to queue the document.
    """

    model_config = ConfigDict(
        extra="allow",
    )
    async_: Annotated[
        bool | None,
        Field(
            alias="async",
            description="Queue the document for asynchronous parsing and return 202 with a job id.",
        ),
    ] = False


class ParseMultipartRequest(BaseModel):
    file: Annotated[bytes, Field(description="The document to parse.")]
    options: Annotated[
        Options1 | None,
        Field(
            description='Parse options as a JSON-encoded string. Currently supports `{"async": true}` to queue the document.'
        ),
    ] = None


class ParseProgress(BaseModel):
    """
    Live progress while a polled async job is in flight.
    """

    percentage: Annotated[int, Field(description="Completion percentage [0, 100].")]
    pages_processed: Annotated[int, Field(description="Pages parsed so far.")]


class ParseResult(BaseModel):
    pages: list[Page]


class ParseUsage(BaseModel):
    pages_processed: int


class PatchedFileUpdateRequestSerializerV3(BaseModel):
    """
    Request serializer for PATCH /api/v3/files/{id} endpoint.

    Allows partial updates to mutable document fields:
    - title: Update the document title
    - tags: Replace ALL tags for the document (both manual and auto-assigned)
    - external_metadata: Create or update external source metadata

    Immutable fields (if provided, will return 400):
    - file, filename, workspace_id, parser, etc.
    """

    title: Annotated[
        str | None, Field(description="Updated title for the document.", max_length=255)
    ] = None
    tags: Annotated[
        list[int] | None,
        Field(
            description="List of tag IDs to replace ALL existing tags (both manual and auto-assigned). To remove all tags when using multipart format, send [0] as the sentinel value."
        ),
    ] = None
    external_metadata: Annotated[
        ExternalMetadataRequest | None,
        Field(
            description="External source metadata to create or update. `external_id` is required when no external metadata record exists yet. Fields in `additional_metadata` are merged (not replaced) with existing values."
        ),
    ] = None


class RelevanceScoringEnum(StrEnum):
    """
    * `none` - none
    * `scoring_only` - scoring_only
    * `scoring_and_filtering` - scoring_and_filtering
    """

    none = "none"
    scoring_only = "scoring_only"
    scoring_and_filtering = "scoring_and_filtering"


class RoleEnum(StrEnum):
    """
    * `viewer` - viewer
    * `editor` - editor
    * `owner` - owner
    """

    viewer = "viewer"
    editor = "editor"
    owner = "owner"


class ScopeTypeEnum(StrEnum):
    """
    * `workspace` - workspace
    * `global` - global
    """

    workspace = "workspace"
    global_ = "global"


class SearchBbox(BaseModel):
    page_number: Annotated[
        int, Field(description="1-indexed page the rectangle sits on.")
    ]
    x: Annotated[float, Field(description="Left edge in PDF points, top-left origin.")]
    y: Annotated[
        float,
        Field(
            description="Top edge in PDF points, top-left origin (y extends downward)."
        ),
    ]
    width: Annotated[float, Field(description="Width in PDF points.")]
    height: Annotated[float, Field(description="Height in PDF points.")]
    unit: Annotated[
        str, Field(description='Coordinate unit. Always "pdf_point" in v1.')
    ]
    origin: Annotated[
        str, Field(description='Coordinate origin. Always "top_left" in v1.')
    ]


class SearchExternalMetadata(BaseModel):
    external_id: Annotated[
        str, Field(description="ID of the document in the external system.")
    ]
    external_url: Annotated[
        str | None,
        Field(
            description="Deep-link back to the document in the source system. Null if not provided."
        ),
    ]
    additional_metadata: Annotated[
        dict[str, Any],
        Field(
            description="Freeform connector metadata. external_url is lifted to its own field and excluded here."
        ),
    ]


class SearchImage(BaseModel):
    b64_content: Annotated[
        str,
        Field(
            description="Base64-encoded page image. Empty string when no vision index exists for the page."
        ),
    ]


class SearchRequest(BaseModel):
    """
    DRF serializer mixin providing ``content_type`` and ``attribute`` fields.

    Compose into any request serializer via multiple inheritance::

        class SearchRequestSerializer(FacetFilterFieldsMixin, serializers.Serializer):
            query = serializers.CharField(...)
            # content_type and attribute inherited from the mixin
    """

    content_type: Annotated[
        list[str] | None,
        Field(
            description="Filter by content type path. Multiple values are OR. Exact-or-subtree matching by default (e.g. `legal` matches legal, legal:contract). Wildcards: `*contract*` (contains), `legal:contract*` (prefix)."
        ),
    ] = None
    attribute: Annotated[
        list[str] | None,
        Field(
            description="Filter by attribute value. **Repeated `attribute` entries are ANDed; values inside one entry are ORed with `|`** (pipe is the recommended OR delimiter — comma also works but can be ambiguous with multi-key values). Example: `attribute=fiscal_year:2024|2025&attribute=status:active` → (fiscal_year 2024 OR 2025) AND (status active). Formats: `name` (has any value), `name:value` (exact), `name:>value` / `name:>=value` (gt/gte), `name:<value` / `name:<=value` (lt/lte), `name:prefix*` (starts with, case-insensitive), `name:*text*` (contains, case-insensitive), `name:a|b` (OR). Smart dates: `filing_date:2023` (year), `filing_date:2023-06` (month). Type-aware: booleans (true/false), multi-select (membership check). Scoped: `content_type(legal:compliance).regulation:AML`."
        ),
    ] = None
    query: Annotated[
        str,
        Field(
            description="Natural-language search query. Maximum 4000 characters.",
            max_length=4000,
        ),
    ]
    max_results: Annotated[
        int | None,
        Field(
            description="Maximum number of chunks to return after reranking. Range: 1–100.",
            ge=1,
            le=100,
        ),
    ] = 10
    workspace_id: Annotated[
        list[int] | None,
        Field(
            description="Restrict search to these workspace IDs. Cannot combine with file_id."
        ),
    ] = None
    tag_id: Annotated[
        list[int] | None,
        Field(
            description="Restrict to documents carrying any of these tag IDs (OR). Cannot combine with file_id."
        ),
    ] = None
    file_id: Annotated[
        list[int] | None,
        Field(
            description="Restrict to specific file IDs. Cannot combine with workspace_id or tag_id."
        ),
    ] = None
    mode: Annotated[
        ModeEnum | None,
        Field(
            description='"text": hybrid keyword + vector search. "vision": VLM-embedded page image search.\n\n* `text` - text\n* `vision` - vision'
        ),
    ] = "text"
    relevance_scoring: Annotated[
        RelevanceScoringEnum | None,
        Field(
            description='Controls the relevance scoring step. "scoring_and_filtering" (default): Score candidates for relevance and only return those above the quality threshold. When no candidate clears the threshold, the few best-scoring candidates are returned instead of an empty result; their scores.relevance is then below the usual threshold. "scoring_only": Score every candidate for relevance but return them all, even low-scoring ones. Useful for building your own filtering logic. "none": Skip the relevance scoring step and return all candidates unfiltered. Fastest option, useful when you handle scoring yourself. Omit the field for the default; send "none" to skip. Overrides skip_rerank when both are sent.\n\n* `none` - none\n* `scoring_only` - scoring_only\n* `scoring_and_filtering` - scoring_and_filtering'
        ),
    ] = "scoring_and_filtering"
    skip_rerank: Annotated[
        bool | None,
        Field(
            description="Deprecated — use relevance_scoring. true → relevance_scoring=none, false → relevance_scoring=scoring_and_filtering. Ignored when relevance_scoring is provided."
        ),
    ] = None
    include_image: Annotated[
        bool | None,
        Field(description="Append a base64-encoded page image to each result."),
    ] = False
    include_bboxes: Annotated[
        bool | None,
        Field(
            description="Append merged bounding boxes (in PDF points, top-left origin) to each result so callers can overlay chunk highlights on PDF pages. PDF documents in text mode only — non-PDF and vision-mode results always return an empty list. Omitted from the response entirely when false."
        ),
    ] = False


class SearchScores(BaseModel):
    text: Annotated[
        float | None,
        Field(
            description="Semantic text similarity (0–1, higher is better). Null in vision mode."
        ),
    ]
    vision: Annotated[
        float | None,
        Field(
            description="Vision page similarity (0–1, higher is better). Null when the document has no vision index."
        ),
    ]
    keyword: Annotated[
        float | None,
        Field(
            description="Keyword match score (higher is better, no fixed upper bound). Null in vision mode."
        ),
    ]
    multivector: Annotated[
        float | None,
        Field(
            description="Token-level similarity score (higher is better, no fixed upper bound). Null when multi-vector scoring is disabled."
        ),
    ]
    relevance: Annotated[
        float | None,
        Field(
            description='Relevance score (0–1, higher is better). Populated when relevance_scoring is "scoring_only" or "scoring_and_filtering". Null when relevance_scoring is "none" or when the scoring model is unavailable.'
        ),
    ]


class SearchTag(BaseModel):
    id: Annotated[int, Field(description="Tag ID.")]
    name: Annotated[str, Field(description="Tag name.")]


class SearchWarning(BaseModel):
    code: Annotated[
        str,
        Field(
            description="Signal name from the scores object that degraded (e.g. 'relevance')."
        ),
    ]
    reason: Annotated[
        str | None,
        Field(
            description="Machine-readable failure reason (model_not_found, timeout, service_error, unknown)."
        ),
    ] = None


class SearchWorkspace(BaseModel):
    id: Annotated[int, Field(description="Workspace ID.")]
    name: Annotated[str, Field(description="Workspace name.")]


class StandardWorkspaceCreateV3Request(BaseModel):
    """
    V3 Request serializer for creating a workspace in the user's company.
    """

    name: Annotated[str, Field(max_length=100)]
    description: str | None = ""


class StandardWorkspaceDatasourceV3RequestTypeEnum(StrEnum):
    googledrive = "googledrive"
    sharepoint = "sharepoint"
    servicenow = "servicenow"
    webscrapper = "webscrapper"


class StatusEnum(StrEnum):
    """
    * `pending` - Pending
    * `pending_conversion` - Pending Conversion
    * `converting` - Converting
    * `parsing` - Parsing
    * `parsing_failed` - Parsing Failed
    * `embedding` - Embedding
    * `embedding_failed` - Embedding Failed
    * `embedded` - Embedded
    * `parsed` - Parsed
    * `fail` - Fail
    * `updating` - Updating
    """

    pending = "pending"
    pending_conversion = "pending_conversion"
    converting = "converting"
    parsing = "parsing"
    parsing_failed = "parsing_failed"
    embedding = "embedding"
    embedding_failed = "embedding_failed"
    embedded = "embedded"
    parsed = "parsed"
    fail = "fail"
    updating = "updating"


class StatusVisionEnum(StrEnum):
    """
    * `pending` - Pending
    * `processing` - Processing
    * `embedded` - Embedded
    * `fail` - Fail
    * `-` - Not available
    """

    pending = "pending"
    processing = "processing"
    embedded = "embedded"
    fail = "fail"
    field_ = "-"


class TagCreateRequestSerializerV3(BaseModel):
    """
    Serializer for creating a tag.
    """

    name: Annotated[str, Field(description="Tag name")]
    description: str
    auto_assign: Annotated[
        bool | None,
        Field(
            description="If True, this tag can be automatically assigned by the system. If False, it can only be assigned by a user."
        ),
    ] = True


class TagItem(BaseModel):
    """
    Serializer for tag items in file list response.
    """

    id: Annotated[int, Field(description="Tag ID")]
    name: Annotated[str, Field(description="Tag name")]
    auto_assigned: Annotated[
        bool,
        Field(
            description="True if this tag was automatically assigned by the system, False if manually assigned by a user"
        ),
    ]


class TagListResponseSerializerV3(BaseModel):
    """
    Serializer for listing tags.
    """

    id: int
    name: Annotated[str, Field(description="Tag name")]
    description: Annotated[
        str, Field(description="Description of the tag (max 500 characters).")
    ]
    auto_assign: Annotated[
        bool,
        Field(
            description="If True, this tag can be automatically assigned by the system. If False, it can only be assigned by a user."
        ),
    ]
    created_at: Annotated[
        AwareDatetime, Field(description="Timestamp when the tag was created.")
    ]
    updated_at: Annotated[
        AwareDatetime, Field(description="Timestamp when the tag was last updated.")
    ]
    document_count: Annotated[
        int, Field(description="Number of visible documents with this tag")
    ]


class TemplateChildNode(BaseModel):
    code: Annotated[str, Field(title="Code")]
    label: Annotated[str, Field(title="Label")]
    description: Annotated[str | None, Field(title="Description")] = ""
    path: Annotated[str, Field(title="Path")]
    inherit_attributes: Annotated[bool | None, Field(title="Inherit Attributes")] = True
    children: Annotated[
        list[TemplateChildNode] | None, Field(title="Children", validate_default=True)
    ] = []


class TemplateRootNode(BaseModel):
    path: Annotated[str, Field(title="Path")]
    code: Annotated[str, Field(title="Code")]
    label: Annotated[str, Field(title="Label")]
    description: Annotated[str | None, Field(title="Description")] = ""
    children: Annotated[
        list[TemplateChildNode] | None, Field(title="Children", validate_default=True)
    ] = []
    attributes: Annotated[
        dict[str, list[AttributeDefResponse]] | None,
        Field(title="Attributes", validate_default=True),
    ] = {}


class UserRoleEnum(StrEnum):
    """
    * `owner` - owner
    * `editor` - editor
    * `viewer` - viewer
    * `` -
    """

    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class WorkspaceDatasourceBrowseV3RequestTypeEnum(StrEnum):
    googledrive = "googledrive"
    sharepoint = "sharepoint"


class WorkspaceInFileResponseSerializerV3(BaseModel):
    """
    Minimal workspace info for file responses.
    """

    id: Annotated[int, Field(description="Workspace ID")]
    name: Annotated[str, Field(description="Workspace name")]
    workspace_type: Annotated[
        str, Field(description="Workspace type (shared or personal)")
    ]


class WorkspaceScopedAPIKey(BaseModel):
    """
    An API key that can access a single workspace, seen from the workspace side.

    Covers both keys explicitly scoped to the workspace (`scope_type="workspace"`,
    each carrying its per-workspace role) and the requesting user's globally-scoped
    keys (`scope_type="global"`), which implicitly reach every workspace in the
    company with the user's own role here. Reads flat dicts built by
    `WorkspaceScopedAPIKeysMixin`, which lists explicitly-scoped keys first.
    """

    id: str
    name: str
    prefix: str
    role: str
    created_at: AwareDatetime
    created_by: str
    scope_type: ScopeTypeEnum


class WorkspaceSummary(BaseModel):
    language: str
    summary: str


class WorkspaceSync(BaseModel):
    datasource_type: str
    source_name: str
    last_status: str
    updated_at: AwareDatetime | None
    failed_files_count: int
    next_import_date: AwareDatetime | None
    editable: bool
    name: str
    instance_url: str | None
    tenant_id: str
    site_name: str
    client_id: str
    filter_criteria: Any


class FieldChunkScoresSchema(BaseModel):
    """
    Per-signal score breakdown. Schema for OpenAPI; higher is better; null = not computed.

    ``text``/``vision`` are 0–1 similarities; ``keyword`` and ``multivector``
    are unbounded (higher is better). Same shape as /api/v3/search and /retrieve.
    ``relevance`` is always null on the file-search path — no relevance scoring
    runs on this endpoint. Defined locally to avoid a circular import with the
    /retrieve serializer module.
    """

    text: Annotated[
        float | None,
        Field(
            description="Semantic text similarity (0–1, higher is better). Null in vision mode."
        ),
    ]
    vision: Annotated[
        float | None,
        Field(
            description="Vision page similarity (0–1, higher is better). Null when the document has no vision index."
        ),
    ]
    keyword: Annotated[
        float | None,
        Field(
            description="Keyword match score (higher is better, no fixed upper bound). Null in vision mode."
        ),
    ]
    multivector: Annotated[
        float | None,
        Field(
            description="Token-level similarity score (higher is better, no fixed upper bound). Null when multi-vector scoring is disabled."
        ),
    ]
    relevance: Annotated[
        float | None,
        Field(
            description="Relevance score (0–1, higher is better). Always null on file search — no relevance scoring runs on this endpoint."
        ),
    ]


class FieldDatasourceConversionRequestTypeEnum(StrEnum):
    """
    * `servicenow` - servicenow
    * `googledrive` - googledrive
    * `sharepoint` - sharepoint
    * `webscrapper` - webscrapper
    """

    servicenow = "servicenow"
    googledrive = "googledrive"
    sharepoint = "sharepoint"
    webscrapper = "webscrapper"


class APIKeyScope(BaseModel):
    workspace_id: int
    workspace_name: str
    workspace_upload_method: str
    workspace_datasource_type: str | None
    role: str
    scope_type: ScopeTypeEnum


class APIKeyScopeRequest(BaseModel):
    """
    One entry in the `scopes` list — a workspace + a role on it.
    """

    workspace_id: Annotated[int, Field(ge=1)]
    role: RoleEnum


class APIKeyV3Response(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: AwareDatetime
    expires_at: AwareDatetime | None
    scopes: list[APIKeyScope]


class AskRequest(BaseModel):
    """
    DRF serializer mixin providing ``content_type`` and ``attribute`` fields.

    Compose into any request serializer via multiple inheritance::

        class SearchRequestSerializer(FacetFilterFieldsMixin, serializers.Serializer):
            query = serializers.CharField(...)
            # content_type and attribute inherited from the mixin
    """

    content_type: Annotated[
        list[str] | None,
        Field(
            description="Filter by content type path. Multiple values are OR. Exact-or-subtree matching by default (e.g. `legal` matches legal, legal:contract). Wildcards: `*contract*` (contains), `legal:contract*` (prefix)."
        ),
    ] = None
    attribute: Annotated[
        list[str] | None,
        Field(
            description="Filter by attribute value. **Repeated `attribute` entries are ANDed; values inside one entry are ORed with `|`** (pipe is the recommended OR delimiter — comma also works but can be ambiguous with multi-key values). Example: `attribute=fiscal_year:2024|2025&attribute=status:active` → (fiscal_year 2024 OR 2025) AND (status active). Formats: `name` (has any value), `name:value` (exact), `name:>value` / `name:>=value` (gt/gte), `name:<value` / `name:<=value` (lt/lte), `name:prefix*` (starts with, case-insensitive), `name:*text*` (contains, case-insensitive), `name:a|b` (OR). Smart dates: `filing_date:2023` (year), `filing_date:2023-06` (month). Type-aware: booleans (true/false), multi-select (membership check). Scoped: `content_type(legal:compliance).regulation:AML`."
        ),
    ] = None
    query: Annotated[
        str,
        Field(
            description="Natural-language question. Maximum 1500 characters.",
            max_length=1500,
        ),
    ]
    max_results: Annotated[
        int | None,
        Field(
            description="Maximum number of chunks to retrieve for context. Range: 1–50.",
            ge=1,
            le=50,
        ),
    ] = 10
    workspace_id: Annotated[
        list[int] | None,
        Field(
            description="Restrict search to these workspace IDs. Cannot combine with file_id."
        ),
    ] = None
    tag_id: Annotated[
        list[int] | None,
        Field(
            description="Restrict to documents carrying any of these tag IDs (OR). Cannot combine with file_id."
        ),
    ] = None
    file_id: Annotated[
        list[int] | None,
        Field(
            description="Restrict to specific file IDs. Cannot combine with workspace_id or tag_id."
        ),
    ] = None
    relevance_scoring: Annotated[
        RelevanceScoringEnum | None,
        Field(
            description='Controls the relevance scoring step used during retrieval. "none": Skip scoring — lowest latency, relevance score is null in each result. "scoring_only": Score every candidate but return them all. Omit for the default (score and filter).\n\n* `none` - none\n* `scoring_only` - scoring_only\n* `scoring_and_filtering` - scoring_and_filtering'
        ),
    ] = "scoring_and_filtering"
    stream: Annotated[
        bool | None,
        Field(description="When true, response is streamed as Server-Sent Events."),
    ] = False
    model: Annotated[
        str | None,
        Field(
            description="LLM used for answer generation. Standard values:\n- `mistral-large-latest`: Mistral Large 2 — flagship general-purpose model. Best answer quality (default).\n- `alfred-ft5`: Alfred FT5 — LightOn fine-tuned model, lighter and faster for straightforward questions.\nCustom model technical names (e.g. `custom-{company_id}-{uuid}`) are also accepted."
        ),
    ] = "mistral-large-latest"


class BatchResponse(BaseModel):
    results: Annotated[list[BatchResultItem], Field(title="Results")]


class BrowseFolderItem(BaseModel):
    """
    A single folder entry returned by the datasource browse endpoint.
    """

    id: Annotated[
        str,
        Field(
            description="Provider folder identifier (SharePoint item id or Google Drive file id)."
        ),
    ]
    name: Annotated[str, Field(description="Folder display name.")]
    has_children: Annotated[
        bool,
        Field(
            description="Best-effort hint for the tree UI: True when the folder is known or assumed to contain subfolders."
        ),
    ]
    path: Annotated[
        str | None,
        Field(
            description="Full path from the drive root (SharePoint only). Null for Google Drive."
        ),
    ] = None
    drive_id: Annotated[
        str | None,
        Field(
            description="SharePoint drive containing the folder. Set for items returned inside a document library; null for library entries themselves and for Google Drive."
        ),
    ] = None
    kind: Annotated[
        KindEnum | None,
        Field(
            description="Item kind. SharePoint root returns 'library' entries (document libraries); everything else is 'folder'.\n\n* `library` - library\n* `folder` - folder"
        ),
    ] = "folder"


class ContentTypeActionRequest(BaseModel):
    """
    Request body for POST /api/v3/content-types.

    Action-dispatched per FAC0012. Every action is idempotent.

    Schema-side verb family:
      - ``adopt`` — bulk import from the Pydantic seed catalog.
      - ``define_content_type`` / ``undefine_content_type`` — CRUD on tree nodes.
      - ``define_attribute`` / ``undefine_attribute`` — CRUD on attribute columns.

    Fields are validated per action in ``validate_fields_for_action`` — top-level
    optionality mirrors the union of action shapes, so consumers only need a
    single Pydantic class (friendly to drf-spectacular), but the validator
    enforces the narrow contract per action, the same pattern used by
    ``FileFacetActionRequest``.
    """

    action: Annotated[ContentTypeActionRequestActionEnum, Field(title="Action")]
    content_types: Annotated[list[str] | None, Field(title="Content Types")] = []
    parent_path: Annotated[str | None, Field(title="Parent Path")] = None
    code: Annotated[str | None, Field(title="Code")] = None
    content_type_path: Annotated[
        str | None,
        Field(
            description="Colon-separated content type path.", title="Content Type Path"
        ),
    ] = None
    label: Annotated[
        str | None,
        Field(
            description="Human-readable label for the node or attribute.", title="Label"
        ),
    ] = None
    description: Annotated[
        str | None,
        Field(
            description="Optional descriptive text for the node or attribute.",
            title="Description",
        ),
    ] = None
    inherit_attributes: Annotated[
        bool | None,
        Field(
            description="Whether child content types inherit attributes from ancestors. Defaults to true on create.",
            title="Inherit Attributes",
        ),
    ] = None
    name: Annotated[
        str | None,
        Field(description="Attribute identifier in snake_case.", title="Name"),
    ] = None
    attribute_type: Annotated[
        str | None,
        Field(
            description="Public attribute type. Supported values: text, number, date, boolean, select, multi-select, rich-text. Accepted aliases: multi_select, multiselect, rich_text, richtext.",
            title="Attribute Type",
        ),
    ] = None
    required: Annotated[
        bool | None,
        Field(
            description="Whether the attribute is required. Defaults to false.",
            title="Required",
        ),
    ] = None
    choices: Annotated[
        list[str] | None,
        Field(
            description="Required for select and multi-select attributes. Must be omitted for all other types.",
            title="Choices",
        ),
    ] = None


class ContentTypeBatchRequest(BaseModel):
    """
    Batch request for content-type schema operations.

    All actions are validated upfront before any execution begins.
    """

    actions: Annotated[
        list[ContentTypeActionRequest],
        Field(max_length=50, min_length=1, title="Actions"),
    ]


class ContentTypeWrite200Response(
    RootModel[ContentTypesListResponse | ContentTypeNodeResponse | AttributeDefResponse]
):
    root: ContentTypesListResponse | ContentTypeNodeResponse | AttributeDefResponse


class CreateAPIKeyV3Request(BaseModel):
    """
    Reject any request fields not declared on the serializer.
    """

    name: Annotated[str, Field(max_length=250)]
    expires_at: Annotated[
        AwareDatetime | None,
        Field(
            description="Expiration datetime for the API key. Set to a future datetime to expire the key at that time, or null to create a key that never expires."
        ),
    ]
    scopes: Annotated[
        list[APIKeyScopeRequest] | None,
        Field(
            description="Optional list of `{workspace_id, role}` entries. Providing this field marks the key as workspace-scoped: it can only access the listed workspaces, with the per-workspace role shown. The requested role on each workspace is capped at the role you currently hold there."
        ),
    ] = None


class CreateAPIKeyV3Response(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: AwareDatetime
    expires_at: AwareDatetime | None
    scopes: list[APIKeyScope]
    key: str


class DocumentSummaryResponse(BaseModel):
    language: Annotated[
        LanguageEnum | None,
        Field(
            description="Language of the summary.\n\n* `en` - English\n* `fr` - French\n* `es` - Spanish\n* `it` - Italian\n* `ar` - Arabic\n* `nl` - Dutch\n* `sv` - Swedish\n* `de` - German\n* `ja` - Japanese\n* `zh` - Chinese\n* `ko` - Korean"
        ),
    ] = None
    summary: Annotated[str, Field(description="Summary of the document.")]


class ExtractJobResponse(BaseModel):
    id: Annotated[str, Field(title="Id")]
    status: Annotated[str, Field(title="Status")]
    created_at: Annotated[AwareDatetime | None, Field(title="Created At")] = None
    completed_at: Annotated[AwareDatetime | None, Field(title="Completed At")] = None
    processing_time_ms: Annotated[int | None, Field(title="Processing Time Ms")] = None
    document: ExtractDocument | None = None
    result: ExtractResult | None = None
    usage: ExtractUsage | None = None
    progress: JobProgress | None = None


class FileCreateResponseSerializerV3(BaseModel):
    id: int
    filename: Annotated[str, Field(description="Filename of the document")]
    workspace: Annotated[
        WorkspaceInFileResponseSerializerV3 | None,
        Field(description="Workspace the document belongs to"),
    ]
    summaries: Annotated[
        list[DocumentSummaryResponse],
        Field(description="Document summaries (all languages)"),
    ]
    title: Annotated[str | None, Field(max_length=255)] = None
    extension: Annotated[str, Field(description="File extension of the document")]
    status: StatusEnum | None = None
    status_vision: StatusVisionEnum | None = None
    created_at: Annotated[
        AwareDatetime, Field(description="Creation date of the resource")
    ]
    updated_at: AwareDatetime
    total_pages: Annotated[int, Field(description="Total number of pages")]
    tags: Annotated[
        list[TagItem], Field(description="List of tags associated with the document")
    ]
    created_by: Annotated[
        CreatedBy | None,
        Field(
            description="User who created the file. Null when the file was created by the system."
        ),
    ]
    upload_session_uuid: Annotated[
        UUID | None,
        Field(description="Upload session UUID associated with this document"),
    ]
    external_metadata: Annotated[
        ExternalMetadataResponse | None, Field(description="External document metadata")
    ]
    message: Annotated[str, Field(description="Status message about the file upload")]


class FileFacetActionRequest(BaseModel):
    """
    Write operation for a file's facets (classifications + attribute values).

    Explicit verb-noun actions per FAC0012:
      - ``classify`` / ``unclassify``: T2 (file ↔ content type)
      - ``set_value`` / ``clear_value``: T3 (attribute value under an assigned content type)

    Value actions require ``attribute_name``; classification actions require only
    ``content_type_path``.
    """

    action: Annotated[FileFacetActionRequestActionEnum, Field(title="Action")]
    content_type_path: Annotated[
        str,
        Field(
            description="Assigned content type path, e.g. legal:contract:nda.",
            title="Content Type Path",
        ),
    ]
    attribute_name: Annotated[
        str | None,
        Field(
            description="Attribute identifier in snake_case.", title="Attribute Name"
        ),
    ] = None
    value: Annotated[
        Any | None,
        Field(
            description="Attribute value for set_value. Shape depends on attribute type: text/rich-text=string, number=number, date=date string (YYYY-MM-DD), boolean=true/false, select=string from choices, multi-select=array of strings from choices.",
            title="Value",
        ),
    ] = None


class FileFacetBatchRequest(BaseModel):
    """
    Batch request for file facet operations.

    All actions are validated upfront before any execution begins.
    """

    actions: Annotated[
        list[FileFacetActionRequest],
        Field(max_length=50, min_length=1, title="Actions"),
    ]


class FileRetrieveResponseSerializerV3(BaseModel):
    id: int
    filename: Annotated[str, Field(description="Filename of the document")]
    workspace: Annotated[
        WorkspaceInFileResponseSerializerV3 | None,
        Field(description="Workspace the document belongs to"),
    ]
    summaries: Annotated[
        list[DocumentSummaryResponse],
        Field(description="Document summaries (all languages)"),
    ]
    title: Annotated[str | None, Field(max_length=255)] = None
    extension: Annotated[str, Field(description="File extension of the document")]
    status: StatusEnum | None = None
    status_vision: StatusVisionEnum | None = None
    created_at: Annotated[
        AwareDatetime, Field(description="Creation date of the resource")
    ]
    updated_at: AwareDatetime
    total_pages: Annotated[int, Field(description="Total number of pages")]
    size: Annotated[int | None, Field(description="Size of the file in bytes.")] = None
    tags: Annotated[
        list[TagItem], Field(description="List of tags associated with the document")
    ]
    created_by: Annotated[
        CreatedBy | None,
        Field(
            description="User who created the file. Null when the file was created by the system."
        ),
    ]
    upload_session_uuid: Annotated[
        UUID | None,
        Field(description="Upload session UUID associated with this document"),
    ]
    signature: Annotated[
        str | None, Field(description="TLSH hash for duplicate detection.")
    ]
    content: Annotated[
        str | None,
        Field(
            deprecated=True,
            description="Deprecated — use `pages[]` instead. Full text content of the document, derived from per-page text, as a single flat string. Only included when include_content=true query parameter is provided. Will be removed in a future release.",
        ),
    ] = None
    pages: Annotated[
        list[Page] | None,
        Field(
            description="Per-page document text in the canonical `{ index, markdown }` shape shared with /parse and /ocr. Only included when include_content=true. Intended replacement for the flat `content` string. For documents ingested before per-page text was stored, the full `content` is returned as a single page (index 1); empty only when there is no content at all."
        ),
    ] = None
    status_detail: Annotated[
        str | None,
        Field(
            description="Detailed error information. Only present when document processing has failed."
        ),
    ] = None
    parser: Annotated[
        str | None,
        Field(
            description="Parser/ingestion pipeline used for document processing (e.g., 'v2.1', 'v3.0'). "
        ),
    ] = None
    external_metadata: Annotated[
        ExternalMetadataResponse | None, Field(description="External document metadata")
    ] = None
    content_types: Annotated[
        list[DocumentFacetCompactSchema],
        Field(
            description="Facet content types with nested attribute values. Excludable via ?exclude=content_types."
        ),
    ]


class PaginatedAPIKeyV3ResponseList(BaseModel):
    count: Annotated[int, Field(examples=[123])]
    next: Annotated[
        AnyUrl | None, Field(examples=["http://api.example.org/accounts/?page=4"])
    ] = None
    previous: Annotated[
        AnyUrl | None, Field(examples=["http://api.example.org/accounts/?page=2"])
    ] = None
    results: list[APIKeyV3Response]


class PaginatedTagListResponseSerializerV3List(BaseModel):
    count: Annotated[int, Field(examples=[123])]
    next: Annotated[
        AnyUrl | None, Field(examples=["http://api.example.org/accounts/?page=4"])
    ] = None
    previous: Annotated[
        AnyUrl | None, Field(examples=["http://api.example.org/accounts/?page=2"])
    ] = None
    results: list[TagListResponseSerializerV3]


class ParseJobStatus(BaseModel):
    """
    Returned by ``GET /api/v3/parse/<id>`` — async parse job status + (once terminal) result.

    Same shape as the sync ``ParseResponseSerializer`` but with completion fields
    (``result``, ``usage``, ``completed_at``, ``processing_time_ms``,
    ``document.page_count``) allowed to be null while the job is still in flight,
    plus an ``error`` block populated only on terminal failure.
    """

    id: str
    status: str
    created_at: AwareDatetime
    completed_at: AwareDatetime | None
    processing_time_ms: int | None
    document: ParseDocument | None
    result: ParseResult | None
    usage: ParseUsage | None
    progress: ParseProgress | None
    error: ParseError | None


class ParseResponse(BaseModel):
    """
    Synchronous ``POST /api/v3/parse`` response — the parse completed inline.
    """

    id: str
    status: str
    created_at: AwareDatetime
    completed_at: AwareDatetime
    processing_time_ms: int
    document: ParseDocument
    result: ParseResult
    usage: ParseUsage


class PatchedUpdateAPIKeyV3Request(BaseModel):
    """
    Reject any request fields not declared on the serializer.
    """

    name: Annotated[str | None, Field(max_length=250)] = None
    scopes: Annotated[
        list[APIKeyScopeRequest] | None,
        Field(
            description="Replace the key's full scope set. Pass an empty list to unscope the key. Each entry's role is re-validated against your current role on the workspace."
        ),
    ] = None


class RelevantChunkScoredV3(BaseModel):
    """
    Relevant chunk with the unified scoring shape, aligned with /api/v3/search.

    Exposes ``score`` + ``scores`` (text/vision/keyword/multivector/relevance) instead of
    the legacy final_score/lexical_score/distance. ``scores.relevance`` is always null on
    this path — no relevance scoring runs on file search.
    """

    text: Annotated[str, Field(description="Chunk text content")]
    chunk_type: Annotated[
        str | None, Field(description="Chunk type (e.g. text/table)")
    ] = None
    score: Annotated[
        float,
        Field(
            description="Combined retrieval score (higher is better, no fixed upper bound). No relevance scoring runs on file search."
        ),
    ]
    scores: FieldChunkScoresSchema


class SearchDetails(BaseModel):
    """
    Serializer for search details in file list response.
    """

    relevant_chunks: Annotated[
        list[RelevantChunkScoredV3],
        Field(description="Relevant chunks ordered by score descending"),
    ]


class SearchSource(BaseModel):
    file_id: Annotated[int, Field(description="File ID.")]
    filename: Annotated[str, Field(description="Original filename.")]
    title: Annotated[str | None, Field(description="Document title.")]
    mime_type: Annotated[str | None, Field(description="File type (e.g. pdf, docx).")]
    size_bytes: Annotated[int | None, Field(description="File size in bytes.")]
    page_start: Annotated[
        int | None, Field(description="Start page of the chunk (1-indexed).")
    ]
    page_end: Annotated[
        int | None, Field(description="End page of the chunk (1-indexed).")
    ]
    total_pages: Annotated[int, Field(description="Total pages in the document.")]
    tags: Annotated[
        list[SearchTag], Field(description="Tags associated with the document.")
    ]
    content_types: Annotated[
        list[dict[str, Any]] | None,
        Field(description="Facet content type classifications and attribute values."),
    ] = None
    external_metadata: Annotated[
        SearchExternalMetadata | None,
        Field(
            description="Null for directly-uploaded documents; present for connector-imported documents."
        ),
    ]


class StandardWorkspaceDatasourceV3Request(BaseModel):
    """
    Pydantic request model for datasource conversion and credential testing.
    """

    type: Annotated[StandardWorkspaceDatasourceV3RequestTypeEnum, Field(title="Type")]
    name: Annotated[str, Field(title="Name")]
    credentials: Annotated[dict[str, Any] | None, Field(title="Credentials")] = {}
    filter_criteria: Annotated[
        dict[str, Any] | None, Field(title="Filter Criteria")
    ] = {}


class StandardWorkspaceV3DetailsResponse(BaseModel):
    """
    V3 Response serializer for company workspace creation and retrieval.
    """

    id: int
    name: str
    workspace_type: str
    document_upload_method: str
    description: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    files_count: int
    user_role: UserRoleEnum | BlankEnum
    used_storage: float
    summaries: list[WorkspaceSummary]
    sync: WorkspaceSync | None
    scoped_api_keys: list[WorkspaceScopedAPIKey]


class StandardWorkspaceV3ListResponse(BaseModel):
    """
    V3 Response serializer for user-level workspaces endpoint.
    """

    id: int
    name: str
    workspace_type: str
    document_upload_method: str
    description: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    files_count: int
    user_role: UserRoleEnum | BlankEnum
    sync: WorkspaceSync | None
    scoped_api_keys: list[WorkspaceScopedAPIKey]


class TemplateListResponse(BaseModel):
    content_types: Annotated[list[TemplateRootNode], Field(title="Content Types")]
    playbooks: Annotated[dict[str, Any] | None, Field(title="Playbooks")] = None


class WorkspaceDatasourceBrowseV3Request(BaseModel):
    """
    Pydantic request model for browsing the remote folder hierarchy of a datasource.

    Only browsable providers (Google Drive, SharePoint) are accepted. Credentials are
    validated against the same models as the credential test endpoint.
    """

    type: Annotated[WorkspaceDatasourceBrowseV3RequestTypeEnum, Field(title="Type")]
    credentials: Annotated[dict[str, Any] | None, Field(title="Credentials")] = {}
    drive_id: Annotated[str | None, Field(title="Drive Id")] = None
    parent_id: Annotated[str | None, Field(title="Parent Id")] = None


class WorkspaceDatasourceBrowseV3Response(BaseModel):
    """
    V3 Response serializer for the datasource folder browse endpoint.
    """

    folders: list[BrowseFolderItem]


class FieldDatasourceConversionRequest(BaseModel):
    """
    Nested serializer for documentation of the datasource conversion payload.
    """

    type: Annotated[
        FieldDatasourceConversionRequestTypeEnum,
        Field(
            description="Datasource provider.\n\n* `servicenow` - servicenow\n* `googledrive` - googledrive\n* `sharepoint` - sharepoint\n* `webscrapper` - webscrapper"
        ),
    ]
    name: Annotated[str, Field(description="Display name for the datasource.")]
    credentials: Annotated[
        dict[str, Any] | None,
        Field(
            description="Provider credentials. googledrive: service_account_file (JSON string). sharepoint: client_id, client_secret, tenant_id, site_id (opt), site_name (opt), instance_url (opt). servicenow: instance_url, username, password. webscrapper: none required."
        ),
    ] = None
    filter_criteria: Annotated[
        dict[str, Any] | None,
        Field(
            description="Provider filter criteria. googledrive: folder_id (required), recursive (opt). sharepoint: folder_path (required), recursive (opt). servicenow: doc_type (required, e.g. 'knowledge'). webscrapper: start_url (required)."
        ),
    ] = None


class AskResultItem(BaseModel):
    chunk_id: Annotated[UUID, Field(description="Chunk UUID.")]
    content: Annotated[
        str | None,
        Field(description="Chunk text content. Null for vision-mode chunks."),
    ]
    score: Annotated[
        float,
        Field(
            description="Effective relevance score — the sort key. Equals scores.relevance (0–1) when relevance scoring ran, otherwise the combined retrieval score (higher is better, no fixed upper bound). Results are ordered by this value descending."
        ),
    ]
    scores: Annotated[SearchScores, Field(description="Per-signal score breakdown.")]
    image: Annotated[
        SearchImage | None,
        Field(description="Page image. Present only when include_image=true."),
    ] = None
    source: Annotated[SearchSource, Field(description="Source document metadata.")]
    workspace: Annotated[
        SearchWorkspace | None, Field(description="Workspace the document belongs to.")
    ]
    bboxes: Annotated[
        list[SearchBbox] | None,
        Field(
            description="Merged bounding boxes for the chunk's text on the source PDF. Present only when include_bboxes=true. Empty list for vision-mode, non-PDF, or pre-v2.2.1 chunks."
        ),
    ] = None
    warnings: Annotated[
        list[SearchWarning] | None,
        Field(
            description="Present only when a pipeline signal degrades. Absent in the happy path."
        ),
    ] = None


class FileListResponseSerializerV3(BaseModel):
    id: int
    filename: Annotated[str, Field(description="Filename of the document")]
    workspace: Annotated[
        WorkspaceInFileResponseSerializerV3 | None,
        Field(description="Workspace the document belongs to"),
    ]
    summaries: Annotated[
        list[DocumentSummaryResponse] | None,
        Field(description="Document summaries (all languages)"),
    ] = None
    title: Annotated[str | None, Field(max_length=255)] = None
    extension: Annotated[str, Field(description="File extension of the document")]
    status: StatusEnum | None = None
    status_detail: Annotated[
        str | None,
        Field(
            description="Detailed error information. Only present when document processing has failed."
        ),
    ] = None
    status_vision: StatusVisionEnum | None = None
    created_at: Annotated[
        AwareDatetime, Field(description="Creation date of the resource")
    ]
    updated_at: AwareDatetime
    total_pages: Annotated[int, Field(description="Total number of pages")]
    size: Annotated[int | None, Field(description="Size of the file in bytes.")] = None
    tags: Annotated[
        list[TagItem], Field(description="List of tags associated with the document")
    ]
    created_by: Annotated[
        CreatedBy | None,
        Field(
            description="User who created the file. Null when the file was created by the system."
        ),
    ]
    upload_session_uuid: Annotated[
        UUID | None,
        Field(description="Upload session UUID associated with this document"),
    ]
    search_details: Annotated[
        SearchDetails | None,
        Field(
            description="Only present when search_details=true and search is provided."
        ),
    ] = None
    signature: Annotated[
        str | None,
        Field(
            description="TLSH hash for duplicate detection. Only included when include_details=true (detail field)."
        ),
    ] = None
    parser: Annotated[
        str | None,
        Field(
            description="Parser/ingestion pipeline used for document processing (e.g., 'v2.1', 'v3.0'). Only included when include_details=true (detail field)."
        ),
    ] = None
    external_metadata: Annotated[
        ExternalMetadataResponse | None, Field(description="External document metadata")
    ] = None
    content_types: Annotated[
        list[DocumentFacetCompactSchema],
        Field(
            description="Facet content types with nested attribute values. Excludable via ?exclude=content_types."
        ),
    ]


class PaginatedFileListResponseSerializerV3List(BaseModel):
    count: Annotated[int, Field(examples=[123])]
    next: Annotated[
        AnyUrl | None, Field(examples=["http://api.example.org/accounts/?page=4"])
    ] = None
    previous: Annotated[
        AnyUrl | None, Field(examples=["http://api.example.org/accounts/?page=2"])
    ] = None
    results: list[FileListResponseSerializerV3]


class PaginatedStandardWorkspaceV3ListResponseList(BaseModel):
    count: Annotated[int, Field(examples=[123])]
    next: Annotated[
        AnyUrl | None, Field(examples=["http://api.example.org/accounts/?page=4"])
    ] = None
    previous: Annotated[
        AnyUrl | None, Field(examples=["http://api.example.org/accounts/?page=2"])
    ] = None
    results: list[StandardWorkspaceV3ListResponse]


class PatchedUpdateWorkspaceV3Request(BaseModel):
    name: Annotated[
        str | None,
        Field(
            description="Workspace name (max 100 characters, cannot be empty). When sent together with `deleted_at: null` (restore), the workspace is restored under this name — used to resolve a collision when the original name was re-taken by a live workspace during the grace period."
        ),
    ] = None
    description: Annotated[
        str | None,
        Field(
            description="Workspace description. Send empty string or null to clear. May be sent together with `deleted_at: null` (restore) to set the description as part of the restore request; a name collision rejects the whole request before the description is applied. `members` and `datasource` are not accepted on a restore request — restore first, then PATCH them."
        ),
    ] = None
    members: Annotated[
        Any | None,
        Field(
            description='Members with roles in format {"users": [{"id": <user_id>, "role": "owner|editor|viewer"}, ...], "groups": [{"id": <group_id>, "role": "owner|editor|viewer"}, ...]}. Role defaults to viewer if not specified. REPLACES all existing members.'
        ),
    ] = None
    datasource: Annotated[
        FieldDatasourceConversionRequest | None,
        Field(
            description="Datasource configuration to convert this workspace into a read-only synced workspace. Workspace OWNER (or a role granting workspace edit/delete) only. Cannot be undone."
        ),
    ] = None


class SearchResultItem(BaseModel):
    chunk_id: Annotated[UUID, Field(description="Chunk UUID.")]
    content: Annotated[
        str | None,
        Field(description="Chunk text content. Null for vision-mode chunks."),
    ]
    score: Annotated[
        float,
        Field(
            description="Effective relevance score — the sort key. Equals scores.relevance (0–1) when relevance scoring ran, otherwise the combined retrieval score (higher is better, no fixed upper bound). Results are ordered by this value descending."
        ),
    ]
    scores: Annotated[SearchScores, Field(description="Per-signal score breakdown.")]
    image: Annotated[
        SearchImage | None,
        Field(description="Page image. Present only when include_image=true."),
    ] = None
    source: Annotated[SearchSource, Field(description="Source document metadata.")]
    workspace: Annotated[
        SearchWorkspace | None, Field(description="Workspace the document belongs to.")
    ]
    bboxes: Annotated[
        list[SearchBbox] | None,
        Field(
            description="Merged bounding boxes for the chunk's text on the source PDF. Present only when include_bboxes=true. Empty list for vision-mode, non-PDF, or pre-v2.2.1 chunks."
        ),
    ] = None


class AskResponse(BaseModel):
    results: Annotated[
        list[AskResultItem],
        Field(
            description="Retrieved chunks used as context, ordered by relevance score descending."
        ),
    ]
    answer: Annotated[
        str,
        Field(description="LLM-generated answer grounded in the retrieved results."),
    ]


class SearchResponse(BaseModel):
    results: Annotated[
        list[SearchResultItem],
        Field(description="Retrieved chunks, ordered by score descending."),
    ]
    warnings: Annotated[
        list[SearchWarning] | None,
        Field(
            description="Present only when a pipeline signal degrades. Absent in the happy path."
        ),
    ] = None
    explain: Annotated[
        dict[str, Any] | None,
        Field(
            description="Scoring breakdown. Present only when explain=true and SEARCH_EXPLAIN_MODE is enabled."
        ),
    ] = None


ContentTypeNodeResponse.model_rebuild()
TemplateChildNode.model_rebuild()
