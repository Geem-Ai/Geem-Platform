# Client Agent SDK contract fixtures

These are executable, exact-version compatibility gates for Phase 14:

- `laravel-ai-v0.10.3` is the minimum supported Laravel AI baseline.
- `laravel-ai-v0.11.0` is the separately pinned current 0.x line at the Phase
  14 implementation date. Do not replace the minimum fixture when adding a
  newer line.
- `openai-python` covers the official OpenAI SDK with the Agent base URL,
  static Expert header, slash-containing Models detail route, non-streaming,
  and streaming tool calls.

The Laravel fixtures deliberately use the standard `openai-compatible`
provider. They must capture both client-to-Geem requests and Geem-to-provider
payloads across the initial call and the tool-result continuation. A manual
example is not a substitute for these tests.

CI runs each exact client through
`tests/integration/test_agent_sdk_live.py`. That harness serves the production
FastAPI app on loopback with real Postgres paid admission and uses a local
HTTP/SSE server as the only OpenRouter transport stub. Its ASGI wrapper records
the caller-to-Geem wire (hashing the bearer value), while the OpenRouter stub
records Geem's upstream payloads. Both non-streaming and fragmented streaming
tests replay two parallel local-tool results; the OpenAI fixture also exercises
Models list/detail and typed SDK exceptions.

Run a prepared fixture from `apps/api` with:

```bash
GEEM_SDK_TARGET=laravel-ai-v0.10.3 pytest -q tests/integration/test_agent_sdk_live.py
GEEM_SDK_TARGET=laravel-ai-v0.11.0 pytest -q tests/integration/test_agent_sdk_live.py
GEEM_SDK_TARGET=openai-python pytest -q tests/integration/test_agent_sdk_live.py
```

These commands require the repository test Postgres database, installed
Composer vendors for both Laravel fixtures, and the OpenAI lock installed into
`openai-python/.venv`. The workflow performs those setup steps explicitly.

Dependency files are generated and committed. CI installs from the lock files;
it never resolves a floating SDK release.
