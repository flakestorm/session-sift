# Examples

## Example: session file

```json
{
  "messages": [
    { "role": "system", "content": "You are a coding assistant." },
    { "role": "user", "content": "Please inspect ./src/app.py" },
    { "role": "assistant", "content": "Great, I will now check that file for you." }
  ]
}
```

Run it:

```bash
session-sift refine session.json --output refined.json
```

## Example: OpenClaw proxy

```bash
session-sift proxy --provider openclaw --upstream-url http://localhost:3000
```

Then point your client at the local proxy URL.

## Example: Python SDK

```python
import asyncio
from session_sift import SessionSiftSDK


async def main():
    sdk = SessionSiftSDK()
    messages = [
        {"role": "system", "content": "You are a coding assistant."},
        {"role": "user", "content": "Review ./src/main.py"},
    ]
    refined, report = await sdk.refine(messages)
    print(refined)
    print(report.to_dict())


asyncio.run(main())
```

## Example: DNA continuity

```bash
session-sift dna-export --output .session-sift/dna.json
session-sift dna-import .session-sift/dna.json
```
