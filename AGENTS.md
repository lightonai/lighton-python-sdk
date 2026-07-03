# AGENTS.md

Design decisions for the LightOn Python SDK. Read before changing architecture.

> **Maintenance rule:** whenever a change alters file architecture (moving/adding/
> removing modules or packages) or a design-pattern decision recorded here, update
> this file in the **same** change — keep it in sync, don't defer it. If a change
> contradicts a decision below, edit the decision and its rationale, don't just append.

## Layout

```
lighton/
  __init__.py        # public exports: LightOn, LightOnConfiguration, Workspace
  _client.py         # LightOn client: httpx wrapper, _request, lifecycle — composes verb mixins
  utils.py           # request-body helpers (_compact, _ids) shared by the verbs
  verbs/             # one primary verb per file, each a mixin on LightOn
    _base.py         # _VerbClient: declares _request (LightOn provides the real one)
    ask.py search.py parse.py extract.py
  exceptions.py      # exception tree
  _active_record.py  # _ActiveRecord base: shared list/get/refresh/delete/_bind/_api/_absorb
  workspace.py       # Workspace — active-record, lives at root
  apikey.py          # ApiKey / ApiKeyScope — active-record, lives at root
  tag.py             # Tag — active-record (list/create/delete only; no single GET)
  content_type.py    # ContentType/Facet/Attribute — content-type taxonomy + file facets
  file.py            # File — active-record + wait_all(); upload = ingestion
  job.py             # ParseJob/ExtractJob — client-bound async handles you poll()
  enums.py           # curated StrEnum vocabularies (FileStatus, Role) shared by resources
  types/             # PURE DATA schemas only (no behavior)
    client/configuration.py   # LightOnConfiguration
    api/__init__.py           # GENERATED pydantic models (do not hand-edit)
tests/               # pytest
Makefile             # make test, make gen-types
```

Rule: `types/` holds pure pydantic data schemas. Anything with logic/behavior
(like `Workspace`) goes at the package root, not under `types/`.

`enums.py` holds hand-curated controlled vocabularies (`FileStatus`, `Role`) used as
model field types. **`StrEnum`, not `Enum`** — members are strings, so `f.status ==
"embedded"` and set-membership keep working without `.value`, and pydantic
serializes them back to plain strings for request bodies. Values mirror the generated
api enums (`StatusEnum`/`RoleEnum`); if the server vocab changes, `make gen-types`
surfaces it and you update `enums.py` by hand. Only enum a field whose full domain is
known — `workspace_type`/`document_upload_method` stay `str` (plain `str` in the schema
too, no documented value set).

## Client

- **Sync only.** `httpx.Client`. No async client until a real event-loop caller needs one — `_request` is the only logic to mirror.
- **One `_request`** does auth header, error mapping (→ raises), and JSON parse. All calls route through it. A 2xx body that isn't JSON → `MalformedResponseError`.
- **Primary verbs** live one-per-file in `verbs/` as mixins (`AskMixin`/`SearchMixin`/`ParseMixin`/`ExtractMixin`) composed onto `LightOn`. Each references `self._request`; the stub on `_VerbClient` (their shared base) makes them type-check in isolation, and `LightOn._request` overrides it at runtime. Keeps `_client.py` to just the transport core. They take explicit typed params and return the generated response models via `model_validate`. `ask`/`search` take `workspaces`/`tags`/`files` (lists of `Workspace`/`Tag`/`File` objects or bare ids; `_ids()` in `utils.py` coerces via duck-typed `.id` → the API's `workspace_id`/`tag_id`/`file_id`; server-side, `file_id` can't combine with `workspace_id`/`tag_id`, and `tag_id` is OR-matched). `parse` takes keyword-only `path` XOR `url` (multipart vs JSON body; raises `ValueError` unless exactly one). `extract` takes keyword-only `path` XOR `url` (multipart vs JSON body; raises `ValueError` unless exactly one — same as `parse`) plus a `schema` that is **either a pydantic model class** or a **raw JSON-Schema dict**; returns `ExtractJobResponse`. The multipart `file` upload isn't in the OpenAPI schema (`ExtractRequest` models only `document`/`schema`/`options`) but the endpoint accepts it — verified by curl; on multipart, `schema`/`options` ride as JSON-encoded form fields alongside the `file` part. Schema handling (in `utils.py`): a dict is validated against the draft-2020-12 meta-schema via `jsonschema` (`validate_response_format_json`, raises `SchemaError`) and otherwise passed through; a pydantic model is converted to a vLLM guided-generation `response_format` schema by `convert_pydantic_to_response_format_json` — `model_json_schema()` then normalized: `$defs`/`$ref` inlined (`_inline_refs`), nullable `anyOf` collapsed to `type: [X, "null"]` (`_collapse_nullable`), draft-2020-12 `$schema` marker added. `jsonschema` is a runtime dep (meta-schema validation is its job; hand-rolling would be flimsy). Ceiling: `_inline_refs` recurses through refs, so a self-referential model would overflow — fine, guided-gen grammars can't express unbounded recursion anyway.
- **Async jobs.** `parse`/`extract` take `mode: ExecMode` (default `ExecMode.SYNC`); `ExecMode.ASYNC` (uppercase members — value `"async"`, and lowercase `async` can't be a member name) sends `options={"async": true}`. `ExecMode` lives in `enums.py` (StrEnum, exported). Async returns a **pollable job handle** (`job.py`): `parse(mode=ASYNC)` → `ParseJob`, `extract(mode=ASYNC)` → `ExtractJob`; sync returns the full response model as before. Each verb has two `@overload`s keyed on `mode: Literal[ExecMode.SYNC|ASYNC]` so callers get the exact return type (`ParseResponse` vs `ParseJob`) instead of the union — the impl signature keeps the `ExecMode` default and the `... | ...Job` return. `Job.poll(page=None)` GETs `<path>/<id>`, absorbs the response onto itself in place (mirrors `_ActiveRecord._absorb`), returns self; `.done` (terminal, `completed_at` set) and `.succeeded` (`status == completed`) read state. `_Job` is a hand-written curated model (`extra="ignore"`) holding the shared plumbing + fields; `ParseJob`/`ExtractJob` subclass it ONLY because `result` differs (`ParseResult.pages` vs `ExtractResult.data`, whose optional fields make a union ambiguous) — parse also has `error`. The job binds to the client via the `_VerbClient` transport surface (all it needs is `_request`), not a full `LightOn` (keeps the mixin's `self` assignable without a cast). `JobStatus` (enums.py) has only the documented `pending`/`completed` — the API doesn't publish the failure vocab, so it's for call-site comparison (StrEnum, unknown server values compare unequal, never validated onto the field), and the "poll until `.succeeded`, raise once `.done`" pattern keys off `completed_at`, not a failure string. No auto-wait helper — callers loop with `time.sleep` (see README); add one if asked.
- Deferred: tag/content_type/attribute filters, streaming — add the params when needed.
- **Config object.** Non-essential knobs (`base_url`, `timeout`, `retries`, `transport`) live in `LightOnConfiguration` (pydantic, `arbitrary_types_allowed`). `api_key` stays a direct `LightOn()` arg; falls back to `LIGHTON_API_KEY` env.
- **Retries** via `httpx.HTTPTransport(retries=)` — connection errors only, exponential backoff. No 5xx/429 retry yet.
- **Timeout** default: `connect=5s`, read/write/pool `120s`.
- **URLs**: `base_url = https://api.lighton.ai` (no version), paths carry the full `/api/v3/...`. Keep the version in the path, NOT base_url — a leading-slash path against a base with a path segment triggers httpx's RFC-3986 join replacement.
- `transport=` injection exists so tests use `httpx.MockTransport` with no network.

## Exceptions

`LightOnError` base → `LightOnConnectionError` (transport) and `LightOnAPIError`
(non-2xx, carries `status_code`/`body`) → `AuthenticationError` (401/403),
`NotFoundError` (404), `RateLimitError` (429), `ServerError` (5xx).
`exceptions.from_response()` maps status → class. `MalformedResponseError`
(sibling of `LightOnAPIError`, not a subclass) — a 2xx body that isn't JSON.

## Resource management: active-record

Chosen pattern (user preference) over a resource-manager. Shared plumbing lives in the
`_ActiveRecord(BaseModel)` base (`_active_record.py`); `Workspace`/`ApiKey`/`File` subclass it.

- **Base provides** the read-side + client-binding: `list`/`get` (classmethods), `refresh`,
  `delete`, `_bind`, `_api`, `_absorb`, `_bound_client`, the `_client` PrivateAttr, and
  `model_config = extra="ignore"`. Subclasses set two ClassVars — `_base` (URL path) and
  `_resource` (name used in the not-persisted `ValueError`).
- **Subclasses provide** only what genuinely diverges: the field schema, `create()`
  (JSON body vs multipart), and `save()` (per-resource PATCH payload).
- Instance methods manage lifecycle: `create(client)` binds the client (`PrivateAttr`);
  `save()`/`refresh()`/`delete()` reuse it. `list`/`get` are classmethods (no instance yet)
  — this asymmetry is inherent to active-record.
- `id` is declared `int | str | None` on the base (so base methods type-check) and
  **narrowed per subclass** (`int | None` for Workspace/File, `str | None` for ApiKey).
- Operating on a non-persisted instance (no id/client) raises `ValueError` via `_bound_client()`.
- `list()` follows pagination fully — no silent truncation. It takes `**params` query
  filters (e.g. `File.list(client, workspace_id=…)`); no typed per-resource override
  because `list` is invariant in its element type — a `list[File]`-returning override
  isn't LSP-assignable to the base's `list[Self]`, and ty rejects it.
- `_absorb` overwrites **only fields present in the response**, so one-time/local-only
  fields survive a later `refresh()` (see ApiKey.key, File.path below).
- Curated schema is **independent of the generated api types** (`extra="ignore"` drops noisy response fields). Hand-written models give stable, clean DX; generated ones are ugly and get regenerated.

`ApiKey` follows the same shape. Its one nuance: the plaintext secret (`key`, a
`SecretStr` — read via `.get_secret_value()`, and it won't leak in logs/`repr`) is
returned only by `create()`, once — `_absorb` only overwrites fields present in the
response, so a later `refresh()` (whose response omits `key`) doesn't wipe it.

`File` follows the same shape with two divergences:
- **`create()` is a multipart upload** (`files=`/`data=`), not a JSON body — uploading
  a file to a workspace IS the ingestion. The returned File carries a processing
  `status`; poll it via `refresh()`/`wait()`. There is **no separate ingestion-job
  resource** — the File is the job, so we don't model one.
- `wait()` blocks on a `time.sleep` poll loop until a terminal status (sync SDK; no
  webhook exists). Ingestion is **non-blocking by default** — `Workspace.ingest(file)`
  and `File.create()` return immediately with status `pending`; only `wait=True` /
  `wait()` block. `wait_all()` (module-level, `ThreadPoolExecutor`) waits on many at once.
- `tags` is a `create()` **argument**, not a model field — the response returns tags as
  objects (not the `list[int]` the request takes), which would clash on `_absorb`.
- **`get_by_name(client, filename, *, workspace)`** fetches the one file with an exact
  filename in a workspace (`workspace` = object or id). The API's `filename` filter is a
  case-insensitive *partial* match, so results are narrowed to an exact `filename` match
  client-side, then required to be unique — raises `ValueError` on no extension, missing
  workspace id, or a non-unique (0 or >1) match.
- **`tag()`/`untag()`** assign/remove tags post-upload; both accept `Tag` objects, ids,
  **or names** via `tag.resolve_ids(client, ...)` — names are resolved through a single
  `Tag.list()` and an unknown name raises `ValueError` (fail loud, not silent no-tag).
  Resolution only lists when a name is present (ids/objects cost no extra call). `tag()`
  POSTs `{"tags": [...]}` to `/files/<id>/tags` and absorbs the returned file; `untag()`
  DELETEs `/files/<id>/tags/<tag_id>` **one per tag** (no bulk delete). Empty is a no-op
  (add endpoint requires `minItems: 1`). File still models no `tags` field, so neither
  reflects tags locally.

`Tag` is a partial active-record: the API is **list/create/delete only** — there's no
`GET /tags/<id>`, so the inherited `get()`/`refresh()` are overridden to raise
`NotImplementedError` rather than 404 at runtime. `create()` posts name/description/
auto_assign. Tags scope `ask`/`search` via `tags=` (OR-matched `tag_id`).

## Content types & facets

`content_type.py` holds three curated read models (`extra="ignore"`, no active-record —
these aren't CRUD resources): `ContentType` (a taxonomy node: `path`/`code`/`label`/
`attributes`/`children`, self-referential — `ContentType.model_rebuild()` resolves the
forward ref), `Attribute` (shared name/type/value/choices shape, `value` None for a bare
definition), and `Facet` (a content type assigned to a file + its attribute values).
`ContentType.list(client, path=/depth=/include_attributes=/query=)` GETs `/content-types`
— the endpoint returns a **tree** (`{content_types: [...]}`), not paginated, so it can't
use `_ActiveRecord.list`.

`File` classification (all via `POST /files/<id>/facets` with an `action`): `classify`/
`unclassify` (assign/remove a content type — T2), `set_attribute`/`clear_attribute` (an
attribute value under an assigned type — T3), each accepting a `ContentType` or a path
string (one `_facet(action, ct, **extra)` helper builds the body). `facets()` GETs the
file's assigned types as `list[Facet]`. Like tags, File models no facet fields locally.

If adding new resources, subclass `_ActiveRecord`: set `_base`/`_resource`, declare the
field schema (narrow `id`), and add `create()`/`save()`. Everything else is inherited.
Only push behavior down into the base when a new resource actually shares it — don't
generalize speculatively for a shape only one subclass needs.

## Generated types

- `make gen-types` runs `datamodel-code-generator` → `lighton/types/api/__init__.py`.
- **Download the schema first**, don't use `--url`: the schema's `$ref` trailing-slash mismatch breaks URL-based resolution.
- Uses `--formatters ruff-check ruff-format` (no black/isort dep), `--use-annotated`, real Enum classes.
- Generated dir is **excluded from ty** (`[tool.ty.src]`): it's machine output validated by pydantic at runtime; chasing type-checker-perfect codegen isn't worth it. Call sites are still type-checked.
- Treat the file as read-only; re-run `make gen-types` to update.

## Conventions

- **Absolute imports only** (`from lighton.x import y`), no relative. Caveat: keep any runtime `LightOn` import inside a function or `TYPE_CHECKING` to avoid cycles (`__init__` imports `_client`).
- **No inline imports** — all imports at module top. (Test self-checks went to `tests/` precisely so their imports could be top-level without circular issues.)
- **Tests**: pytest, fixtures + `pytest.raises`. `pythonpath = ["."]` so tests import the source tree directly (independent of the editable-install finder, which goes stale when new modules are added). Mock HTTP via `httpx.MockTransport`.
- **Tooling**: ruff (lint + format), ty (type check), pytest — all enforced via pre-commit. `ty` has no autofix; it blocks on errors.
- **uv.lock**: re-stage it after any dependency change before committing, or the ty pre-commit hook (which runs through `uv` and re-resolves) will report a lockfile modification and fail the commit.
- New deps: prefer stdlib → installed dep → a few lines, before adding anything. Mark deliberate simplifications with `ponytail:` comments.
- Non-trivial logic leaves one runnable test behind.
- **Docstrings (public API)**: every public function/method has a docstring documenting
  each argument and the return value (Google-style `Args:`/`Returns:`, plus `Raises:`
  when it raises deliberately). `self`/`cls` are omitted. Private helpers (`_`-prefixed)
  and self-evident one-liners are exempt — don't pad them. Keep it about behavior and
  contract, not a restatement of the signature.
- **Model fields**: every field on a hand-written pydantic model carries a
  `Field(description=...)` — the description is the field's documentation (drives IDE
  hints, JSON schema, and generated docs). Use `Field` keyword args for the default too
  (`Field(None, description=...)`, `Field(default_factory=list, description=...)`); don't
  mix a bare default with a `Field`. This applies to the curated schemas at the package
  root, NOT the generated `types/api/` (regenerated) — those already carry descriptions
  from the OpenAPI schema.
