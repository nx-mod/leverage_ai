# AGENTS.md — leverage_ai v2.0

## Project Overview

`leverage_ai` is a modular Python package implementing a multi-provider AI pipeline. It routes requests across 9 free/cheap-tier LLM APIs with smart caching, conversation memory, depletion tracking, and colored terminal output.

## Package Structure

```
leverage_ai/
  __init__.py       Package metadata (version, author)
  __main__.py       Entry point — main loop, arg parsing
  config.py         All constants, API keys, chains, costs
  exceptions.py     Typed exception hierarchy (ProviderError subclasses)
  colors.py         ANSI color helpers for terminal output
  providers.py      Per-provider HTTP wrappers + response parsers
  orchestrator.py   Chain routing, try_chain(), run_stage(), classify()
  pipelines.py      Task pipelines (chat, quick, code, write, analyze)
  cache.py          Exact + semantic similarity caching (7-day TTL)
  memory.py         Persistent memory + conversation history
  state.py          Usage state (tokens, depletion, daily reset)
  code_utils.py     Code block extraction, file saving, execution
  commands.py       In-app commands (remember/forget/show memory/usage)
  usage.py          Session usage display + startup banner
```

## Running

```bash
python -m leverage_ai                  # Interactive mode
python -m leverage_ai --noexec         # Skip code execution prompts
python -m leverage_ai --debug          # Enable debug logging
python -m leverage_ai --help

# After pip install -e .:
leverage-ai
```

## Architecture

### Classification → Pipeline dispatch

`classify(idea)` calls Groq cheaply to pick a category, then falls back to keyword matching:

| Category  | Pipeline                 | Provider chain                          |
|-----------|--------------------------|------------------------------------------|
| `chat`    | single stage             | Groq → Qwen → HuggingFace → Cloudflare  |
| `quick`   | single stage             | HuggingFace → Groq → Cloudflare         |
| `code`    | Spec → Arch → Build → Review (short: just Build) | Qwen → Charm Hyper → HuggingFace → Groq → Mistral |
| `write`   | Draft → Final            | Groq/Qwen → Charm Hyper/Qwen/Groq/Mistral |
| `analyze` | Analysis → Deeper        | Qwen → Groq → HuggingFace → Mistral → Cloudflare |

### Provider flow (`try_chain`)

1. Sort chain by least-used providers (token counts from state)
2. Apply minute-offset rotation to avoid always hitting same provider
3. For each provider: call function → handle typed exceptions → check HTTP status → parse response
4. On 401/403/429/402: mark provider as depleted in state, skip future
5. On 5xx or connection error: try next provider
6. Return first successful `(provider_name, content)`

### Exception hierarchy

```
ProviderError
  ProviderAuthError        — no key or 401/403
  ProviderRateLimit        — 429/402
  ProviderTimeout          — requests.Timeout
  ProviderConnectionError  — requests.ConnectionError
  ProviderResponseError    — bad response structure from parser
  ProviderNotAvailable     — explicitly marked unavailable
```

`providers.py` raises typed exceptions from `call()` and from parser functions.  
`orchestrator.py` catches them separately to decide whether to deplete or just skip.

### State files (all in `~`)

| File                    | Contents                                 |
|-------------------------|------------------------------------------|
| `~/.leverage_ai.env`    | API keys (never committed)               |
| `~/.leverage_usage.json`| Token counts, depletion list, daily reset|
| `~/.leverage_memory.json`| Stored facts and preferences            |
| `~/.leverage_convo.json`| Last 20 conversation turns               |
| `~/.leverage_cache/`    | MD5-keyed JSON response cache            |
| `~/ai_output/`          | Saved generated code files               |

## Key Patterns

### Adding a new provider

1. Add API key var to `config.py` (`MY_KEY = os.getenv("MY_API_KEY")`)
2. Add function + parser to `providers.py`; raise `ProviderAuthError` if no key
3. Add entry to `PROVIDERS` dict in `providers.py`
4. Add name to `ALL_PROVIDERS` list in `config.py`
5. Add to whichever `CHAIN_*` lists make sense in `config.py`

### Adding a new pipeline type

1. Add new `CHAIN_*` list in `config.py`
2. Add `pipeline_foo()` in `pipelines.py`
3. Add keyword classifier branch in `orchestrator.py`'s `classify()`
4. Add dispatch case in `__main__.py`'s main loop

## Gotchas

- **`python-dotenv` required**: `config.py` uses `load_dotenv()`. Run `pip install -r requirements.txt` first.
- **No hardcoded account IDs**: `CF_ACCOUNT_ID` must be set in env — no fallback.
- **Code execution**: files saved to `~/ai_output/` run via `subprocess.run(shell=True)` with 60s timeout. No sandboxing.
- **Cache collisions**: MD5 + normalized prompt. Semantic match at 85% ratio for prompts ≤20 words.
- **Depletion resets**: only Cloudflare auto-clears on daily reset. Others stay depleted until you delete `~/.leverage_usage.json`.
- **`usage_log` is a module global**: `usage.py` imports it from `orchestrator.py` — avoid reimporting or you'll get a separate list.
