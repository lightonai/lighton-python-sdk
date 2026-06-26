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

