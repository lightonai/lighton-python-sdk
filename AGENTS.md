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
  _client.py         # LightOn client: httpx wrapper, _request, primary verbs
  exceptions.py      # exception tree
  workspace.py       # Workspace — data + behavior (active-record), lives at root
  apikey.py          # ApiKey / ApiKeyScope — active-record, lives at root
  file.py            # File — active-record + wait_all(); upload = ingestion
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
- **One `_request`** does auth header, error mapping (→ raises), and JSON parse. All calls route through it.
- **Config object.** Non-essential knobs (`base_url`, `timeout`, `retries`, `transport`) live in `LightOnConfiguration` (pydantic, `arbitrary_types_allowed`). `api_key` stays a direct `LightOn()` arg; falls back to `LIGHTON_API_KEY` env.
- **Retries** via `httpx.HTTPTransport(retries=)` — connection errors only, exponential backoff. No 5xx/429 retry yet.
- **Timeout** default: `connect=5s`, read/write/pool `120s`.
- **URLs**: `base_url = https://api.lighton.ai` (no version), paths carry the full `/api/v3/...`. Keep the version in the path, NOT base_url — a leading-slash path against a base with a path segment triggers httpx's RFC-3986 join replacement.
- `transport=` injection exists so tests use `httpx.MockTransport` with no network.

## Exceptions

`LightOnError` base → `LightOnConnectionError` (transport) and `LightOnAPIError`
(non-2xx, carries `status_code`/`body`) → `AuthenticationError` (401/403),
`NotFoundError` (404), `RateLimitError` (429), `ServerError` (5xx).
`exceptions.from_response()` maps status → class.

## Resource management: active-record

Chosen pattern (user preference) for `Workspace`, over a resource-manager:

- Instance methods manage lifecycle: `create(client)` binds the client to the instance (`PrivateAttr`); `save()` (PATCH), `refresh()` (GET), `delete()` reuse it.
- `list(client)` / `get(client, id)` are **classmethods** (no instance yet) — this asymmetry is accepted and inherent to active-record.
- Operating on a non-persisted instance (no id/client) raises `ValueError`.
- `list()` follows pagination fully — no silent truncation.
- Curated schema is **independent of the generated api types** (`extra="ignore"` drops noisy response fields). Hand-written models give stable, clean DX; generated ones are ugly and get regenerated.

`ApiKey` follows the same shape. Its one nuance: the plaintext secret (`key`) is
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

If adding new resources, follow the same active-record shape for consistency.
**The list/get/_bind/_absorb/_api plumbing is now duplicated across `workspace.py`,
`apikey.py`, and `file.py`** — still a deliberate choice over a shared base, because
`File.create` (multipart) and `ApiKey`'s one-time-secret `_absorb` diverge enough that
only the read-side is truly identical. Extract a shared `_ActiveRecord` base when a
**fourth** resource lands or the copies start drifting in the shared parts.

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
