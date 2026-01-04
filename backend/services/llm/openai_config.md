# OpenAI API Configuration Guide

**Version:** 2025-01-04
**Purpose:** Comprehensive reference for constructing OpenAI API calls with all available response formats and configurations.

---

## Table of Contents

1. [Authentication & Endpoint](#1-authentication--endpoint)
2. [Basic API Call Structure](#2-basic-api-call-structure)
3. [Request Parameters Reference](#3-request-parameters-reference)
4. [Response Formats](#4-response-formats)
5. [Structured Outputs (JSON Schema)](#5-structured-outputs-json-schema)
6. [Function Calling & Tools](#6-function-calling--tools)
7. [Streaming Responses](#7-streaming-responses)
8. [Token Usage & Optimization](#8-token-usage--optimization)
9. [Common Use Cases & Examples](#9-common-use-cases--examples)

---

## 1. Authentication & Endpoint

### Base URL
```
https://api.openai.com/v1/chat/completions
```

### Authentication
All requests require Bearer token authentication via the `Authorization` header:

```bash
Authorization: Bearer $OPENAI_API_KEY
```

### Headers
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer YOUR_API_KEY"
}
```

---

## 2. Basic API Call Structure

### Minimal Request
```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "user",
      "content": "Hello!"
    }
  ]
}
```

### Complete Request Example
```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "developer",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "Hello!"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "top_p": 1.0,
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "response_format": { "type": "text" },
  "store": false
}
```

### Standard Response Structure
```json
{
  "id": "chatcmpl-123456",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "gpt-4o-2024-08-06",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I assist you today?",
        "refusal": null,
        "annotations": []
      },
      "logprobs": null,
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 19,
    "completion_tokens": 10,
    "total_tokens": 29,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "audio_tokens": 0
    },
    "completion_tokens_details": {
      "reasoning_tokens": 0,
      "audio_tokens": 0,
      "accepted_prediction_tokens": 0,
      "rejected_prediction_tokens": 0
    }
  },
  "service_tier": "default"
}
```

---

## 3. Request Parameters Reference

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model identifier (e.g., "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo") |
| `messages` | array | Array of message objects with `role` and `content` |

### Message Roles

| Role | Description | Usage |
|------|-------------|-------|
| `system` | System instructions (legacy) | Defines assistant behavior |
| `developer` | Developer instructions (preferred) | Replaces `system` in newer models |
| `user` | User input | The user's message |
| `assistant` | Assistant response | Previous responses in conversation |

### Optional Parameters

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `temperature` | number | 0.0 - 2.0 | 1.0 | Controls randomness. Higher = more random |
| `max_tokens` | integer | 1+ | model max | Maximum tokens in response |
| `top_p` | number | 0.0 - 1.0 | 1.0 | Nucleus sampling. Alternative to temperature |
| `frequency_penalty` | number | -2.0 - 2.0 | 0.0 | Penalize token frequency |
| `presence_penalty` | number | -2.0 - 2.0 | 0.0 | Penalize token presence |
| `n` | integer | 1+ | 1 | Number of completions to generate |
| `stop` | string/array | - | null | Stop sequences |
| `stream` | boolean | - | false | Enable streaming responses |
| `logprobs` | boolean | - | false | Include log probabilities |
| `top_logprobs` | integer | 0-20 | null | Number of top log probs to return |
| `seed` | integer | - | null | Deterministic sampling seed |
| `store` | boolean | - | false | Store completion for retrieval |
| `verbosity` | string | low/medium/high | medium | Response conciseness level |

### Caching & Safety Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt_cache_key` | string | Cache key for similar requests (replaces deprecated `user`) |
| `safety_identifier` | string | Unique user/session ID for abuse detection |

### Web Search Integration

```json
{
  "web_search_options": {
    "enabled": true
  }
}
```

---

## 4. Response Formats

OpenAI supports multiple response format configurations:

### 4.1 Text Mode (Default)

```json
{
  "response_format": {
    "type": "text"
  }
}
```

**Response:**
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Plain text response..."
    }
  }]
}
```

### 4.2 JSON Mode (Legacy)

Forces valid JSON output without strict schema validation.

```json
{
  "response_format": {
    "type": "json_object"
  }
}
```

**IMPORTANT:** You MUST instruct the model to output JSON in your system/user message, or the model may generate whitespace infinitely until token limit.

**Example:**
```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "developer",
      "content": "You are a helpful assistant. Always respond with valid JSON."
    },
    {
      "role": "user",
      "content": "Extract the name and age from: John is 30 years old"
    }
  ],
  "response_format": {
    "type": "json_object"
  }
}
```

**Response:**
```json
{
  "choices": [{
    "message": {
      "content": "{\"name\": \"John\", \"age\": 30}"
    }
  }]
}
```

---

## 5. Structured Outputs (JSON Schema)

### Overview

**Structured Outputs** guarantee that model responses conform to your JSON schema. This is the **preferred approach** for reliable, typed responses.

**Supported Models:**
- `gpt-4o-2024-08-06` and later
- `gpt-4-turbo-2024-04-09` and later
- `gpt-3.5-turbo-1106` and later

### 5.1 Basic JSON Schema Format

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "schema_name",
      "schema": {
        "type": "object",
        "properties": {
          "field_name": {
            "type": "string"
          }
        },
        "required": ["field_name"]
      }
    }
  }
}
```

### 5.2 Complete Structured Output Example

**Request:**
```json
{
  "model": "gpt-4o-2024-08-06",
  "messages": [
    {
      "role": "system",
      "content": "Extract event information from the user's message."
    },
    {
      "role": "user",
      "content": "Alice and Bob are going to a science fair on Friday at 3 PM."
    }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "event_extraction",
      "schema": {
        "type": "object",
        "properties": {
          "event_name": {
            "type": "string",
            "description": "Name of the event"
          },
          "date": {
            "type": "string",
            "description": "When the event occurs"
          },
          "time": {
            "type": "string",
            "description": "Time of the event"
          },
          "participants": {
            "type": "array",
            "items": {
              "type": "string"
            },
            "description": "List of participants"
          }
        },
        "required": ["event_name", "date", "participants"],
        "additionalProperties": false
      }
    }
  }
}
```

**Response:**
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "{\"event_name\": \"science fair\", \"date\": \"Friday\", \"time\": \"3 PM\", \"participants\": [\"Alice\", \"Bob\"]}"
    },
    "finish_reason": "stop"
  }]
}
```

### 5.3 Supported JSON Schema Types

| Type | Description | Example |
|------|-------------|---------|
| `string` | Text data | `{"type": "string"}` |
| `number` | Numeric (int/float) | `{"type": "number"}` |
| `integer` | Integer only | `{"type": "integer"}` |
| `boolean` | true/false | `{"type": "boolean"}` |
| `array` | List of items | `{"type": "array", "items": {"type": "string"}}` |
| `object` | Nested object | `{"type": "object", "properties": {...}}` |
| `null` | Null value | `{"type": "null"}` |

### 5.4 Schema Constraints

```json
{
  "type": "string",
  "enum": ["option1", "option2", "option3"],
  "minLength": 3,
  "maxLength": 100,
  "pattern": "^[A-Z].*"
}
```

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 100,
  "multipleOf": 5
}
```

```json
{
  "type": "array",
  "items": {"type": "string"},
  "minItems": 1,
  "maxItems": 10,
  "uniqueItems": true
}
```

### 5.5 Complex Nested Schema Example

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "user_profile",
      "schema": {
        "type": "object",
        "properties": {
          "user": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "age": {"type": "integer", "minimum": 0},
              "email": {"type": "string", "format": "email"}
            },
            "required": ["name", "email"]
          },
          "preferences": {
            "type": "object",
            "properties": {
              "theme": {
                "type": "string",
                "enum": ["light", "dark", "auto"]
              },
              "notifications": {"type": "boolean"}
            }
          },
          "tags": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": true
          }
        },
        "required": ["user"],
        "additionalProperties": false
      }
    }
  }
}
```

---

## 6. Function Calling & Tools

### 6.1 Tool Types

OpenAI supports three categories of tools:

1. **Custom Functions** - User-defined functions with typed parameters
2. **Built-in Tools** - OpenAI-provided tools (web search, file search, code interpreter)
3. **MCP Tools** - Third-party integrations (Google Drive, SharePoint, etc.)

### 6.2 Function Definition Structure

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "function_name",
        "description": "Clear description of what the function does",
        "parameters": {
          "type": "object",
          "properties": {
            "param_name": {
              "type": "string",
              "description": "Parameter description"
            }
          },
          "required": ["param_name"]
        }
      }
    }
  ]
}
```

### 6.3 Complete Function Calling Example

**Request:**
```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "user",
      "content": "What's the weather in Paris and New York?"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get the current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "City and country (e.g., 'Paris, France')"
            },
            "unit": {
              "type": "string",
              "enum": ["celsius", "fahrenheit"],
              "description": "Temperature unit"
            }
          },
          "required": ["location"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

**Response:**
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_abc123",
          "type": "function",
          "function": {
            "name": "get_weather",
            "arguments": "{\"location\": \"Paris, France\", \"unit\": \"celsius\"}"
          }
        },
        {
          "id": "call_def456",
          "type": "function",
          "function": {
            "name": "get_weather",
            "arguments": "{\"location\": \"New York, USA\", \"unit\": \"fahrenheit\"}"
          }
        }
      ]
    },
    "finish_reason": "tool_calls"
  }]
}
```

### 6.4 Tool Choice Options

| Value | Behavior |
|-------|----------|
| `"auto"` | Model decides whether to call functions |
| `"none"` | Model will not call any functions |
| `"required"` | Model must call at least one function |
| `{"type": "function", "function": {"name": "function_name"}}` | Force specific function |

**Examples:**
```json
{
  "tool_choice": "auto"
}
```

```json
{
  "tool_choice": {
    "type": "function",
    "function": {"name": "get_weather"}
  }
}
```

### 6.5 Handling Function Responses

After receiving tool calls, you must:

1. Execute the functions locally
2. Send results back in a new request

**Follow-up Request:**
```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "user",
      "content": "What's the weather in Paris?"
    },
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"location\": \"Paris, France\"}"
        }
      }]
    },
    {
      "role": "tool",
      "tool_call_id": "call_abc123",
      "content": "{\"temperature\": 18, \"condition\": \"sunny\"}"
    }
  ]
}
```

### 6.6 Multiple Tools Example

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get current weather",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"}
          },
          "required": ["location"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "send_email",
        "description": "Send an email message",
        "parameters": {
          "type": "object",
          "properties": {
            "to": {"type": "string", "format": "email"},
            "subject": {"type": "string"},
            "body": {"type": "string"}
          },
          "required": ["to", "body"]
        }
      }
    }
  ]
}
```

---

## 7. Streaming Responses

### 7.1 Enable Streaming

```json
{
  "stream": true
}
```

### 7.2 Stream Response Format

Each chunk is a separate Server-Sent Event (SSE):

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4o","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4o","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4o","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4o","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### 7.3 Streaming with Python

```python
import openai
from openai import OpenAI

client = OpenAI(api_key="your-api-key")

stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
```

### 7.4 Streaming with JavaScript

```javascript
const openai = require('openai');

const client = new openai.OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

async function streamChat() {
  const stream = await client.chat.completions.create({
    model: 'gpt-4o',
    messages: [{ role: 'user', content: 'Tell me a story' }],
    stream: true
  });

  for await (const chunk of stream) {
    const content = chunk.choices[0]?.delta?.content || '';
    process.stdout.write(content);
  }
}

streamChat();
```

---

## 8. Token Usage & Optimization

### 8.1 Token Counting

Response includes detailed token breakdown:

```json
{
  "usage": {
    "prompt_tokens": 19,
    "completion_tokens": 10,
    "total_tokens": 29,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "audio_tokens": 0
    },
    "completion_tokens_details": {
      "reasoning_tokens": 0,
      "audio_tokens": 0,
      "accepted_prediction_tokens": 0,
      "rejected_prediction_tokens": 0
    }
  }
}
```

### 8.2 Prompt Caching

Use `prompt_cache_key` to improve cache hit rates for similar requests:

```json
{
  "prompt_cache_key": "user_session_12345"
}
```

### 8.3 Token Optimization Tips

1. **Use `max_tokens`** - Limit response length
2. **Leverage caching** - Set `prompt_cache_key` for repeated patterns
3. **Concise prompts** - Shorter prompts = fewer tokens
4. **Structured outputs** - Reduces token waste from invalid JSON
5. **Temperature 0** - For deterministic, focused responses

---

## 9. Common Use Cases & Examples

### 9.1 Data Extraction

```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "system",
      "content": "Extract structured information from user input."
    },
    {
      "role": "user",
      "content": "John Doe, john@example.com, age 30, lives in New York"
    }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "user_info",
      "schema": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "email": {"type": "string"},
          "age": {"type": "integer"},
          "city": {"type": "string"}
        },
        "required": ["name", "email"]
      }
    }
  }
}
```

### 9.2 Classification

```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "system",
      "content": "Classify customer feedback sentiment and category."
    },
    {
      "role": "user",
      "content": "The product arrived damaged and customer service was unhelpful."
    }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "feedback_classification",
      "schema": {
        "type": "object",
        "properties": {
          "sentiment": {
            "type": "string",
            "enum": ["positive", "neutral", "negative"]
          },
          "category": {
            "type": "string",
            "enum": ["product_quality", "shipping", "customer_service", "pricing", "other"]
          },
          "urgency": {
            "type": "string",
            "enum": ["low", "medium", "high"]
          }
        },
        "required": ["sentiment", "category", "urgency"]
      }
    }
  }
}
```

### 9.3 Multi-Step Reasoning

```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "developer",
      "content": "Break down complex problems into steps and provide structured reasoning."
    },
    {
      "role": "user",
      "content": "How do I calculate compound interest for $1000 at 5% annually over 3 years?"
    }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "reasoning_steps",
      "schema": {
        "type": "object",
        "properties": {
          "steps": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "step_number": {"type": "integer"},
                "description": {"type": "string"},
                "calculation": {"type": "string"}
              }
            }
          },
          "final_answer": {"type": "string"}
        },
        "required": ["steps", "final_answer"]
      }
    }
  }
}
```

### 9.4 Content Generation with Constraints

```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "developer",
      "content": "Generate marketing content following strict constraints."
    },
    {
      "role": "user",
      "content": "Write a product description for wireless headphones"
    }
  ],
  "max_tokens": 150,
  "temperature": 0.8,
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "marketing_content",
      "schema": {
        "type": "object",
        "properties": {
          "headline": {
            "type": "string",
            "maxLength": 60
          },
          "description": {
            "type": "string",
            "maxLength": 200
          },
          "key_features": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 5
          },
          "cta": {
            "type": "string",
            "maxLength": 30
          }
        },
        "required": ["headline", "description", "key_features", "cta"]
      }
    }
  }
}
```

### 9.5 Conversational Agent with Function Calling

```json
{
  "model": "gpt-4o",
  "messages": [
    {
      "role": "developer",
      "content": "You are a helpful assistant that can check weather and set reminders."
    },
    {
      "role": "user",
      "content": "What's the weather in Tokyo? Also remind me to call mom tomorrow at 3pm."
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"}
          },
          "required": ["location"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "set_reminder",
        "description": "Set a reminder for a specific date and time",
        "parameters": {
          "type": "object",
          "properties": {
            "message": {"type": "string"},
            "datetime": {"type": "string", "format": "date-time"}
          },
          "required": ["message", "datetime"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

### 9.6 Batch Processing Pattern

```python
import openai
from openai import OpenAI
import json

client = OpenAI(api_key="your-api-key")

# Process multiple items with the same schema
items = [
    "Extract: John, john@email.com, 555-1234",
    "Extract: Jane, jane@email.com, 555-5678"
]

schema = {
    "type": "json_schema",
    "json_schema": {
        "name": "contact_info",
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"}
            },
            "required": ["name"]
        }
    }
}

results = []
for item in items:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": item}],
        response_format=schema
    )
    results.append(json.loads(response.choices[0].message.content))

print(results)
```

---

## Finish Reasons

| Reason | Description |
|--------|-------------|
| `stop` | Natural completion or stop sequence reached |
| `length` | Max tokens limit reached |
| `tool_calls` | Model called a function/tool |
| `content_filter` | Content filtered by safety systems |
| `function_call` | (Deprecated) Model called a function |

---

## Model Recommendations

| Model | Best For | Structured Outputs |
|-------|----------|-------------------|
| `gpt-4o` | Latest, most capable | ✅ |
| `gpt-4-turbo` | Fast, cost-effective | ✅ |
| `gpt-4` | High quality reasoning | ❌ (use turbo) |
| `gpt-3.5-turbo` | Speed & low cost | ✅ (limited) |

---

## Error Handling

Common error codes:

| Code | Description | Solution |
|------|-------------|----------|
| 401 | Invalid authentication | Check API key |
| 429 | Rate limit exceeded | Implement backoff |
| 400 | Invalid request | Validate JSON schema |
| 500 | Server error | Retry with backoff |

**Example Error Response:**
```json
{
  "error": {
    "message": "Invalid API key",
    "type": "invalid_request_error",
    "code": "invalid_api_key"
  }
}
```

---

## Quick Reference: Response Format Cheat Sheet

```python
# Text (default)
response_format = {"type": "text"}

# JSON mode (legacy)
response_format = {"type": "json_object"}

# Structured output
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "schema_name",
        "schema": {
            "type": "object",
            "properties": {
                "field": {"type": "string"}
            },
            "required": ["field"]
        }
    }
}
```

---

## Additional Resources

- **OpenAI API Reference:** https://platform.openai.com/docs/api-reference
- **JSON Schema Specification:** https://json-schema.org/
- **Token Pricing:** https://openai.com/api/pricing/
- **Rate Limits:** https://platform.openai.com/docs/guides/rate-limits

---

**Last Updated:** 2025-01-04
**Document Version:** 1.0.0
