# GitHub Models API Research

**Date:** 2026-03-18
**Purpose:** Evaluate GitHub Models API as an LLM provider, specifically for Claude Opus 4.6

> **UPDATE:** Claude Opus 4.6 is not available via GitHub Models API. Instead, we will use
> **GitHub Copilot CLI** (`gh copilot -p "..." -s --model   claude-sonnet-4.6 --no-ask-user`)
> which supports Claude model selection and scriptable plain-text output.
> See: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference

---

## 1. Authentication

GitHub Models API uses **bearer token authentication** with a GitHub Personal Access Token (PAT).

### PAT Setup

1. Go to https://github.com/settings/tokens
2. Create a **fine-grained personal access token** with the `models: read` scope
3. The token format starts with `github_pat_`

### Headers

```
Authorization: Bearer <GITHUB_PAT>
Accept: application/vnd.github+json
Content-Type: application/json
X-GitHub-Api-Version: 2026-03-10
```

### Alternative Auth Methods

- **GitHub Actions:** Use the built-in `GITHUB_TOKEN` (add `permissions: models: read` to the workflow)
- **GitHub App:** Generate a token with the `models: read` scope

**Source:** [Quickstart for GitHub Models](https://docs.github.com/en/github-models/quickstart), [REST API endpoints for models inference](https://docs.github.com/en/rest/models/inference)

---

## 2. API Endpoint and Request Format

### Base URL

```
https://models.github.ai
```

### Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/inference/chat/completions` | POST | Chat completions (general) |
| `/orgs/{org}/inference/chat/completions` | POST | Chat completions (org-attributed) |
| `/catalog/models` | GET | List available models |

### Request Body

```json
{
  "model": "{publisher}/{model_name}",
  "messages": [
    { "role": "system", "content": "You are a helpful assistant." },
    { "role": "user", "content": "Hello" }
  ],
  "temperature": 0.7,
  "max_tokens": 1024,
  "stream": false
}
```

### Full curl Example

```bash
curl -X POST https://models.github.ai/inference/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  -d '{
    "model": "openai/gpt-4.1",
    "messages": [
      {"role": "user", "content": "What is the capital of France?"}
    ]
  }'
```

### Optional Parameters

| Parameter | Type | Description |
|---|---|---|
| `temperature` | float (0-1) | Controls randomness |
| `top_p` | float (0-1) | Nucleus sampling |
| `max_tokens` | int | Maximum response length |
| `stream` | bool | Enable streaming (SSE) |
| `stop` | array | Stop sequences |
| `seed` | int | For deterministic sampling |
| `frequency_penalty` | float (-2 to 2) | Reduces token repetition |
| `presence_penalty` | float (-2 to 2) | Encourages new tokens |
| `response_format` | object | JSON/structured output format |
| `tools` | array | Function/tool definitions |
| `tool_choice` | string | Tool usage control ("auto", "required", "none") |

**Source:** [REST API endpoints for models inference](https://docs.github.com/en/rest/models/inference)

---

## 3. Claude Opus 4.6 Availability

### FINDING: Claude models are NOT available through GitHub Models API

Based on thorough research, **Anthropic Claude models are not currently available in the GitHub Models marketplace or API**. Here is what was found:

- The GitHub Models catalog includes models from **OpenAI, Meta (Llama), DeepSeek, Microsoft (Phi), and xAI (Grok)** -- but **not Anthropic**.
- The [GitHub Models pricing page](https://docs.github.com/en/billing/reference/costs-for-github-models) lists 16 models with no Claude models among them.
- The BYOK (Bring Your Own Key) feature only supports **OpenAI and AzureAI** providers -- **not Anthropic**.

### Where Claude IS Available on GitHub

- **GitHub Copilot:** Claude Opus 4.6 is available as a model choice for Copilot Pro, Pro+, Business, and Enterprise users ([changelog](https://github.blog/changelog/2026-02-05-  claude-sonnet-4.6-is-now-generally-available-for-github-copilot/)).
- **GitHub Copilot coding agent:** The Anthropic Claude coding agent (public preview) uses the Claude Agent SDK and is powered by the Copilot subscription.

These integrations are through **GitHub Copilot**, not the GitHub Models inference API. There is no way to call Claude via `models.github.ai`.

### Where Claude IS Available via API

| Platform | Model ID | Endpoint |
|---|---|---|
| Anthropic API | `  claude-sonnet-4.6-20250205` | `https://api.anthropic.com/v1/messages` |
| AWS Bedrock | `anthropic.  claude-sonnet-4.6-20250205-v1:0` | Regional Bedrock endpoints |
| Google Vertex AI | `  claude-sonnet-4.6@20250205` | Regional Vertex endpoints |
| Azure AI Foundry | `  claude-sonnet-4.6` | `https://<resource>.services.ai.azure.com/anthropic/v1/messages` |

**Source:** [Anthropic Claude on GitHub](https://docs.github.com/en/copilot/concepts/agents/anthropic-claude), [Claude Opus 4.6 changelog](https://github.blog/changelog/2026-02-05-  claude-sonnet-4.6-is-now-generally-available-for-github-copilot/), [Azure AI Foundry Claude docs](https://github.com/MicrosoftDocs/azure-ai-docs/blob/main/articles/foundry/foundry-models/how-to/use-foundry-models-claude.md)

---

## 4. Structured Output / JSON Mode

GitHub Models API supports structured output through the `response_format` parameter, compatible with OpenAI's structured output spec.

### Simple JSON Mode

```json
{
  "model": "openai/gpt-4.1",
  "messages": [...],
  "response_format": { "type": "json_object" }
}
```

### JSON Schema Mode (Strict)

```json
{
  "model": "openai/gpt-4.1",
  "messages": [...],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "MySchema",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {
          "title": { "type": "string" },
          "items": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "required": ["title", "items"],
        "additionalProperties": false
      }
    }
  }
}
```

### Python SDK (azure-ai-inference)

```python
from azure.ai.inference.models import JsonSchemaFormat

response = client.complete(
    response_format=JsonSchemaFormat(
        name="Recipe_JSON_Schema",
        schema=json_schema,
        description="Recipe in structured format",
        strict=True,
    ),
    messages=[
        SystemMessage("You are a helpful assistant."),
        UserMessage("Give me a recipe for chocolate cake."),
    ],
)
```

**Note:** Structured output support varies by model. Not all models in the catalog support `json_schema` mode -- check model capabilities via the catalog API.

**Source:** [Azure AI Inference structured output sample](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-inference/samples/sample_chat_completions_with_structured_output.py)

---

## 5. Rate Limits and Token Limits

### Free Tier Rate Limits (Copilot Free/Pro/Business/Enterprise)

| Category | Requests/min | Requests/day | Input tokens/req | Output tokens/req | Concurrent |
|---|---|---|---|---|---|
| **Low models** | 15-20 | 150-450 | 8,000 | 4,000-8,000 | 5-8 |
| **High models** | 10-15 | 50-150 | 8,000-16,000 | 4,000-8,000 | 2-4 |
| **Embedding** | 15-20 | 150-450 | 64,000 | N/A | 5-8 |

- Specialized models (o1, o3, grok-3, deepseek-r1) have more restrictive limits.
- Some models/tiers show "Not applicable" for Copilot Free users.

### Paid Tier

- Opt in to paid usage for **production-grade rate limits** and increased context windows.
- Billing uses a unified **token unit** system: `token_units = (input_tokens * input_multiplier) + (output_tokens * output_multiplier)`.
- Each model has its own input/output multipliers. Prices range from $0.08/$0.30 per 1M tokens (Phi-4-mini) to $3.00/$15.00 per 1M tokens (Grok 3).

### Key Constraints

- Free tier token limits per request (e.g., 8,000 input tokens) are significantly smaller than model context windows.
- Paid tier unlocks larger context windows closer to model maximums.

**Source:** [Prototyping with AI models](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models), [Costs for GitHub Models](https://docs.github.com/en/billing/reference/costs-for-github-models)

---

## 6. Python SDK

### Option A: `azure-ai-inference` (Recommended by GitHub Docs)

This is the official Python SDK referenced in GitHub Models documentation.

```bash
pip install azure-ai-inference
```

```python
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

# For GitHub Models
client = ChatCompletionsClient(
    endpoint="https://models.inference.ai.azure.com",
    credential=AzureKeyCredential(os.environ["GITHUB_TOKEN"]),
    model="openai/gpt-4.1",
)

response = client.complete(
    messages=[
        SystemMessage("You are a helpful assistant."),
        UserMessage("How many feet are in a mile?"),
    ],
)

print(response.choices[0].message.content)
print(f"Tokens used: {response.usage}")
```

**Note on endpoint:** The Python SDK uses `https://models.inference.ai.azure.com` as the endpoint (Azure-hosted backend), while the REST API uses `https://models.github.ai`. Both work with a GitHub PAT.

### Option B: OpenAI Python SDK (Compatible)

Since GitHub Models uses the OpenAI-compatible chat completions format, the OpenAI SDK works with a custom base URL:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=os.environ["GITHUB_TOKEN"],
)

response = client.chat.completions.create(
    model="openai/gpt-4.1",
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
)

print(response.choices[0].message.content)
```

### Option C: Raw `requests`

```python
import requests

response = requests.post(
    "https://models.github.ai/inference/chat/completions",
    headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Content-Type": "application/json",
    },
    json={
        "model": "openai/gpt-4.1",
        "messages": [{"role": "user", "content": "Hello!"}],
    },
)

print(response.json()["choices"][0]["message"]["content"])
```

**Source:** [azure-ai-inference README](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-inference/README.md), [Quickstart for GitHub Models](https://docs.github.com/en/github-models/quickstart)

---

## 7. Summary and Recommendations

### Can we use GitHub Models API for Claude Opus 4.6?

**No.** Claude models are not available through the GitHub Models API (`models.github.ai`). Claude is only available on GitHub through **Copilot** (as a model choice for chat/coding), not through the programmatic inference API.

### Alternatives for Programmatic Claude Opus 4.6 Access

| Option | Pros | Cons |
|---|---|---|
| **Anthropic API directly** | Full feature set, latest models, native SDK | Separate account/billing |
| **AWS Bedrock** | Enterprise features, IAM integration | AWS dependency, slightly delayed model availability |
| **Google Vertex AI** | GCP integration | GCP dependency |
| **Azure AI Foundry** | Azure integration, Microsoft ecosystem | Preview status, Azure dependency |

### If GitHub Models API Is Acceptable (Without Claude)

The GitHub Models API is a solid choice for OpenAI models (GPT-4.1, GPT-4o) with:
- Simple auth via GitHub PAT
- OpenAI-compatible API format
- Structured output support
- Multiple Python SDK options
- Free tier for prototyping

### Recommendation

If Claude Opus 4.6 is required, use the **Anthropic API directly** or one of the cloud provider integrations (Bedrock, Vertex, Azure Foundry). The GitHub Models API cannot serve as a Claude provider.
