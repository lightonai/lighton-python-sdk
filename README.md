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
doc.title = "Q4 Report"
doc.save()
doc.delete()
```

