# lighton-python-sdk

## Quick start

```bash
export LIGHTON_API_KEY="..."
```

```python
import os
from lighton import LightOn

client = LightOn(api_key=os.environ["LIGHTON_API_KEY"]))

answer = client.ask(query="What is LightOn?")
```
