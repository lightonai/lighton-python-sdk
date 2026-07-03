# lighton-python-sdk

## Quick start

```bash
export LIGHTON_API_KEY="..."
```

```python
from lighton import LightOn

client = LightOn()  # reads LIGHTON_API_KEY from the environment

answer = client.ask(query="What is LightOn?")
```

## Primary verbs

`ask`, `search`, `parse`, and `extract` live directly on the client. Scope any
retrieval to workspaces or specific files (objects or bare ids).

```python
from lighton import LightOn, SearchMode

client = LightOn()

# ask — grounded, LLM-generated answer over indexed documents
resp = client.ask("What were Q4 revenues?", workspaces=[42], max_results=5)
print(resp.answer)
for r in resp.results:               # ranked chunks used as context
    print(r.source.filename, r.score)

# search — ranked passages, no generation (scope by workspaces, tags, or files)
resp = client.search("termination clause", tags=[7], mode=SearchMode.text)
for r in resp.results:
    print(r.score, r.content)

# parse — document to per-page Markdown (pass a local path XOR a public URL)
doc = client.parse(path="report.pdf")
# doc = client.parse(url="https://example.com/report.pdf")
for page in doc.result.pages:
    print(page.index, page.markdown)

# extract — structured data guided by a schema (see Extract below)
resp = client.extract(schema=InvoiceModel, path="invoice.pdf")
print(resp.result.data)
```

## Extract

`extract(schema, *, path | url)` pulls structured data from a document — pass a
local `path` to upload (multipart) or a public `url` to fetch, exactly one (same
as `parse`). The `schema` drives guided generation and can be **a pydantic
model** or a **raw JSON-Schema dict** — use whichever you have.

A pydantic model is the easy path: nested models, `list[...]`, and `X | None`
fields all convert to a valid vLLM `response_format` schema for you.

Give every field a meaningful `Field(description=...)` — the descriptions are
carried into the schema and steer the model, so they materially improve
extraction quality. Treat them as instructions, not documentation.

```python
from lighton import LightOn
from pydantic import BaseModel, Field

client = LightOn()


class Person(BaseModel):
    last_name: str = Field(description="Family name, as written in the document.")
    first_name: str | None = Field(
        None, description="Given name; null if not stated."
    )
    role: str | None = Field(
        None, description="Title or role if given, e.g. 'sender', 'recipient'."
    )


class Letter(BaseModel):
    people: list[Person] = Field(
        description="Every person or entity named in the letter."
    )
    subject: str | None = Field(
        None, description="The letter's stated subject line, or null if absent."
    )


resp = client.extract(schema=Letter, path="letter.pdf")
# or from a public URL: client.extract(schema=Letter, url="https://example.com/letter.pdf")
for row in resp.result.data:          # one object per page
    print(row)
```

Or pass the schema dict directly — it's validated against the JSON-Schema
meta-schema (raises `jsonschema.SchemaError` if malformed) and sent as-is:

```python
resp = client.extract(
    url="https://example.com/invoice.pdf",
    schema={
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "total": {"type": "number"},
            "currency": {"type": ["string", "null"]},
        },
        "required": ["total"],
    },
)
print(resp.result.data)
```

Need the converted schema without calling the API (to inspect or cache it)?

```python
from lighton.utils import convert_pydantic_to_response_format_json

schema = convert_pydantic_to_response_format_json(Letter)
```

### Async jobs & polling

Both `parse` and `extract` take `mode=` (an `ExecMode`, default `ExecMode.SYNC`).
Pass `ExecMode.ASYNC` to queue the job — the call returns a `ParseJob` /
`ExtractJob` handle instead of blocking. Call `job.poll()` to refresh it in place;
`job.succeeded` is the one success state and `job.done` means terminal (finished
either way). Handy for large documents that would otherwise time out.

```python
import time

# queue the job — returns right away, job.status == "pending"
job = client.extract(schema=Letter, path="big-scan.pdf", mode=ExecMode.ASYNC)

while not job.poll().succeeded:
    if job.done:                                # terminal but not completed → failure
        raise RuntimeError(f"extract job {job.id} ended as {job.status!r}")
    if job.progress:                            # optional live progress
        print(f"{job.progress.percentage}% ({job.progress.pages_processed} pages)")
    time.sleep(2)

for row in job.result.data:
    print(row)
```

`poll()` mutates the job and returns it, so `while not job.poll().succeeded:`
reads naturally; raising once `job.done` (terminal but not successful) means a
stuck or failed job surfaces instead of looping forever.

`parse` is the same shape — on failure a `ParseJob` carries an `error` block you
can raise with directly:

```python
import time

job = client.parse(path="big.pdf", mode=ExecMode.ASYNC)

while not job.poll().succeeded:
    if job.error is not None:                   # terminal failure
        raise RuntimeError(f"parse job {job.id} failed: {job.error.message}")
    time.sleep(2)

for page in job.result.pages:
    print(page.index, page.markdown)
```

## Workspaces

Workspaces are active-record objects: an instance manages its own lifecycle.

```python
from lighton import LightOn, Workspace

client = LightOn()

# Create
ws = Workspace(name="Legal", description="Contracts & NDAs").create(client)

# Edit, then persist
ws.name = "Legal EU"
ws.save()

# Re-fetch from the API
ws.refresh()

# List (follows pagination) and retrieve by id
for w in Workspace.list(client):
    print(w.id, w.name)

ws = Workspace.get(client, ws.id)

# Delete
ws.delete()
```

## Tags

Tags scope `ask`/`search` to documents carrying them. Active-record style, but
the API is **list/create/delete only** — there's no fetch-by-id, so `get()` /
`refresh()` raise `NotImplementedError`.

Manage tags:

```python
from lighton import LightOn, Tag

client = LightOn()

# Create
contracts = Tag(name="contracts", description="Signed contracts").create(client)

# List (follows pagination)
for t in Tag.list(client):
    print(t.id, t.name, t.document_count)

# Delete
contracts.delete()
```

Assign tags to a file with `tag()` / `untag()`. Both accept **`Tag` objects, bare
ids, or tag names** (mix freely); names are resolved via `Tag.list()` under the
hood and a name that doesn't exist raises `ValueError`:

```python
from lighton import File

doc = File.get_by_name(client, "nda-2026.pdf", workspace=42)

doc.tag([contracts])                 # Tag object
doc.tag([12, 13])                    # bare ids
doc.tag(["contracts", "urgent"])     # names — resolved & existence-checked
doc.tag([contracts, 12, "urgent"])   # mixed

doc.untag(["urgent"])                # remove by name
```

Scope a query to one or more tags (OR-matched — a doc matches if it has any):

```python
answer = client.ask("What are the termination terms?", tags=[contracts])
hits = client.search("indemnification", tags=[contracts.id, 12])
```

## API keys

Same active-record style. The plaintext secret is available **only** right after `create()`.

```python
from lighton import LightOn, ApiKey, ApiKeyScope, Role

client = LightOn()

key = ApiKey(
    name="ci-pipeline",
    scopes=[ApiKeyScope(workspace_id=42, role=Role.viewer)],  # omit for an unscoped key
).create(client)

print(key.key.get_secret_value())  # plaintext secret (SecretStr) — shown once, store it now

# Manage existing keys
for k in ApiKey.list(client):
    print(k.id, k.name, k.prefix)

key = ApiKey.get(client, key.id)
key.name = "ci-pipeline-v2"
key.save()
key.delete()
```

## Files & ingestion

Uploading a file into a workspace *is* the ingestion — there's no separate job to
track. The returned `File` carries a processing `status`; poll it with `refresh()`,
or `wait()` to block until it's embedded. Ingestion is **non-blocking by default**.

```python
from lighton import LightOn, Workspace, File, wait_all

client = LightOn()
ws = Workspace.get(client, 42)

# Upload — returns immediately, f.status == "pending"
f = ws.ingest(File(path="report.pdf"))

f.refresh()          # poll status whenever you like
print(f.status)      # pending → parsing → embedding → embedded

# Or block until ready (opt-in)
ws.ingest(File(path="report.pdf"), wait=True)

# Bulk upload, then wait on all concurrently (threads — the SDK is sync)
files = [ws.ingest(File(path=p)) for p in ("a.pdf", "b.pdf", "c.pdf")]
wait_all(files)

# Manage existing files (active-record, like Workspace/ApiKey)
for doc in File.list(client, workspace_id=42):
    print(doc.id, doc.filename, doc.status)

doc = File.get(client, f.id)

# Or fetch by exact filename within a workspace (must include the extension;
# raises unless exactly one match). workspace takes a Workspace or an id.
doc = File.get_by_name(client, "report.pdf", workspace=42)
doc.title = "Q4 Report"
doc.save()

# Assign / remove tags — by Tag object, id, or name (see Tags below)
doc.tag([7, "contracts"])
doc.untag([12])

doc.delete()
```

