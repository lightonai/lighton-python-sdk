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
  types/             # PURE DATA schemas only (no behavior)
    client/configuration.py   # LightOnConfiguration
    api/__init__.py           # GENERATED pydantic models (do not hand-edit)
tests/               # pytest
Makefile             # make test, make gen-types
```

Rule: `types/` holds pure pydantic data schemas. Anything with logic/behavior
(like `Workspace`) goes at the package root, not under `types/`.

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

If adding new resources, follow the same active-record shape for consistency.

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
