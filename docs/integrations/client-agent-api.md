# Client Agent API

The Geem Client Agent API is an OpenAI Chat Completions-compatible surface for
client-owned tool loops. Geem selects and retrieves knowledge for one Expert,
runs one model round, and returns either assistant text or OpenAI `tool_calls`.
The caller executes every tool and submits the resulting transcript in the next
request. Geem never executes caller-supplied tools.

This is a separate paid App Store product named **Agents AI**. It does not grant
MCP access and purchasing MCP Connectors does not grant this API.

## Requirements

Before a request can run, all of the following must be true:

- `CLIENT_AGENT_API_ENABLED=true` on the API deployment.
- The `agents-ai` catalog App is published, subscribed, and installed for the
  Workspace.
- The API key has the independently selected `agent:write` scope.
- The selected Workspace-owned Expert has **Allow client agent API** enabled.
- The Workspace API RPM, Workspace AI-token allowance, and Agents AI daily
  request allowance all have capacity.

Create or reissue a key after subscribing; scopes are never silently added to
an existing key. Expiry or uninstall leaves the key and Expert setting stored,
but the runtime access check makes them inert immediately.

## Base URL and authentication

Use this base URL, not the answer-mode `/api/v1` base:

```text
https://api.geem.ai/api/v1/agent
```

Every request uses a Workspace API key as a bearer token. Completions also need
the Expert header:

```http
Authorization: Bearer geem_sk_...
X-Geem-Expert-Id: 00000000-0000-0000-0000-000000000000
```

The public model ID is stable:

```text
dalseen/geem-1.0
```

`model` identifies the public model, never the Expert. The Expert comes only
from `X-Geem-Expert-Id` and must belong to the API key's Workspace.

## Model discovery

Models routes need `agent:write` and current paid access, but no Expert header.
They consume no RPM, AI-token, or Agents AI daily unit.

```bash
curl https://api.geem.ai/api/v1/agent/models \
  -H 'Authorization: Bearer geem_sk_...'

curl https://api.geem.ai/api/v1/agent/models/dalseen/geem-1.0 \
  -H 'Authorization: Bearer geem_sk_...'
```

The detail route intentionally accepts a slash inside the model ID.

## One non-streaming round

```bash
curl https://api.geem.ai/api/v1/agent/chat/completions \
  -H 'Authorization: Bearer geem_sk_...' \
  -H 'X-Geem-Expert-Id: 00000000-0000-0000-0000-000000000000' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "dalseen/geem-1.0",
    "messages": [{"role": "user", "content": "Where is order 123?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "lookup_order",
        "description": "Look up an order visible to the current caller",
        "parameters": {
          "type": "object",
          "properties": {"order_id": {"type": "string"}},
          "required": ["order_id"],
          "additionalProperties": false
        }
      }
    }],
    "tool_choice": "auto"
  }'
```

If the response contains `choices[0].message.tool_calls`, execute those tools
inside your application. Preserve each call's `id`, `type`, function name, and
arguments in the assistant message. Then send the full relevant transcript and
the same active tool definitions again:

```json
{
  "model": "dalseen/geem-1.0",
  "messages": [
    {"role": "user", "content": "Where is order 123?"},
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_01H...",
        "type": "function",
        "function": {
          "name": "lookup_order",
          "arguments": "{\"order_id\":\"123\"}"
        }
      }]
    },
    {
      "role": "tool",
      "tool_call_id": "call_01H...",
      "content": "{\"status\":\"shipped\"}"
    }
  ],
  "tools": [{
    "type": "function",
    "function": {
      "name": "lookup_order",
      "parameters": {"type": "object"}
    }
  }]
}
```

Parallel calls are supported. Return exactly one `role: tool` result for every
call from the preceding assistant turn, in any order, before adding another
user or assistant message. Orphaned, duplicate, incomplete, or undeclared calls
are rejected before retrieval or billing admission.

## Stateless replay

The API stores no hidden conversation and requires no proprietary session
header. Every model step must resend the relevant bounded history. At minimum,
retain the latest user message and all assistant/tool messages after it. Geem
scans the real caller-owned transcript for the latest user question; tool
results never become retrieval queries.

A continuation may reuse a short-lived retrieval cache keyed by Workspace,
Expert, API key, question hash, and knowledge revision. Cache loss or a revision
change safely causes retrieval to run again. The cache never stores the tool
transcript and is never an authorization source.

Each HTTP completion is one billable model round and consumes one Agents AI
daily request unit after admission. A loop with three client/model iterations
therefore consumes three units. Client-local tool execution is not metered by
Geem. An admitted unit remains consumed if the provider later fails or the
client disconnects.

## Streaming

Set `stream: true`. The response is standard SSE and ends with
`data: [DONE]`. Tool calls arrive as indexed `delta.tool_calls` fragments. Do
not parse JSON out of text content.

```json
{
  "model": "dalseen/geem-1.0",
  "messages": [{"role": "user", "content": "Where is order 123?"}],
  "tools": [{"type": "function", "function": {
    "name": "lookup_order",
    "parameters": {"type": "object"}
  }}],
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

With `include_usage`, normal chunks have `usage: null`, followed by one
usage-only chunk with `choices: []`, raw model token counts, and the `geem`
extension. Without it, `geem` appears once on the terminal choice chunk.

## Geem response metadata

Successful completions include a namespaced `geem` object. OpenAI-compatible
clients may safely ignore it.

```json
{
  "retrieval": "executed",
  "citations": [],
  "insufficient_context": false,
  "billed_tokens": 1234
}
```

- `retrieval` is `executed`, `cache_hit`, or `skipped_general`.
- `citations` lists metadata-safe sources made available to that model round;
  it does not claim that the assistant cited every source.
- `insufficient_context` is deterministic for RAG Experts and `null` for a
  general-knowledge Expert.
- `billed_tokens` is the Geem-weighted amount. Standard `usage` remains the
  provider's raw prompt/completion/total count.

Do not replay `geem` as a conversation message.

## Laravel AI

Geem supports Laravel AI's standard `openai-compatible` driver; no custom
provider is required. Pin an exact SDK version in production. Geem's contract
matrix retains `v0.10.3` as its minimum supported baseline.

```php
// config/ai.php
'providers' => [
    'geem' => [
        'driver' => 'openai-compatible',
        'url' => env('GEEM_AGENT_URL'),
        'key' => env('GEEM_AGENT_API_KEY'),
        'headers' => [
            'X-Geem-Expert-Id' => env('GEEM_EXPERT_ID'),
        ],
        'models' => [
            'text' => ['default' => 'dalseen/geem-1.0'],
        ],
    ],
],
```

```dotenv
GEEM_AGENT_URL=https://api.geem.ai/api/v1/agent
GEEM_AGENT_API_KEY=geem_sk_...
GEEM_EXPERT_ID=00000000-0000-0000-0000-000000000000
```

Define normal Laravel AI tools on your Agent. Laravel executes them locally and
submits their results on the next Chat Completions request. The API key holder
must be authorized to receive all knowledge exposed by the selected Expert.

## Official OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="geem_sk_...",
    base_url="https://api.geem.ai/api/v1/agent",
    default_headers={
        "X-Geem-Expert-Id": "00000000-0000-0000-0000-000000000000"
    },
)

response = client.chat.completions.create(
    model="dalseen/geem-1.0",
    messages=[{"role": "user", "content": "Summarize the return policy."}],
)
```

Use a second client without the Expert header if desired for Models discovery;
the header is ignored there.

## Instruction and tool-result trust

Leading client `system` and `developer` messages are accepted for SDK
compatibility, but Geem demotes them to one escaped, explicitly untrusted user
block below Geem and Expert policy. They can guide response style and tool use,
but cannot change Workspace identity, Expert selection, access, quota, or
billing. Later or interleaved instruction messages are invalid.

Tool names, descriptions, schemas, arguments, and results are untrusted.
Tool-result content is bounded and escaped while its `role: tool` and
`tool_call_id` remain unchanged. Never put credentials in prompts, tool schemas,
or tool results. Validate tool arguments and authorize every tool inside your
own application before execution.

Client-owned tools can receive model output derived from Expert knowledge. A
prompt hierarchy cannot guarantee that a model never places retrieved content
in tool arguments. Enable the feature only when the API-key holder and its tool
runtime are authorized to receive that Expert's knowledge.

## Supported request controls

Phase 14 accepts `temperature`, `top_p`, `max_tokens`,
`parallel_tool_calls`, `stream_options.include_usage`, `n: 1`, and
`response_format: {"type":"text"}`. Function tools use JSON Schema object
roots and local references only. Remote references, `strict: true`, structured
output, vision/audio content, legacy `functions` / `function_call`, and the
Responses API are rejected explicitly rather than ignored.

All errors use the OpenAI envelope:

```json
{
  "error": {
    "message": "...",
    "type": "invalid_request_error",
    "param": "messages",
    "code": "agent_invalid_tool_transcript"
  }
}
```

Honor `Retry-After` on rate/quota responses. Daily Agents AI quota errors also
include a safe `error.details` extension with `metric`, `limit`, `used`,
`remaining`, and the exact RFC 3339 UTC `reset_at`; SDKs may ignore this
extension, while retry schedulers can use it. A post-HTTP-200 streaming failure
emits one SSE error frame, closes the stream, and does not emit `[DONE]`.
