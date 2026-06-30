# AGENTS.md — leverage_ai v2.2

## Project Overview

`leverage_ai` is a modular Python package implementing a multi-provider AI pipeline. It routes requests across 9 free/cheap-tier LLM APIs with smart caching, conversation memory, depletion tracking, a real function-calling agent mode, and live-reconfigurable provider/chain/sandbox settings via in-app panels.

## Package Structure

```
leverage_ai/
  __init__.py             Package metadata (version, author)
  __main__.py             Entry point — main loop, arg parsing, panel sub-prompts
  config.py                All constants, API keys, chains, chain registry
  exceptions.py            Typed exception hierarchy (ProviderError subclasses)
  colors.py                ANSI color helpers for terminal output
  providers.py             Per-provider HTTP wrappers + response parsers (live key lookup)
  orchestrator.py          Chain routing, try_chain(), run_stage(), classify(), live filtering
  pipelines.py             Task pipelines (chat, quick, code, write, analyze)
  settings.py              /settings store: sandbox, auto-run, semantic cache, debug
  provider_settings.py     /providers store: enable state + live API key overrides
  chain_settings.py        /models store: per-chain provider toggles
  cache.py                 Exact-match caching
  semantic_cache.py        FastEmbed-based fuzzy cache (ONNX runtime, no torch)
  memory.py                Persistent memory + conversation history + relevance scoring
  state.py                 Usage state (tokens, depletion, daily reset)
  code_utils.py            Code block extraction, file saving, sandboxed/unsandboxed execution
  win_sandbox.py           Windows Job Object sandbox backend (ctypes, no pywin32)
  commands.py              In-app commands + /settings, /providers, /models panel renderers
  usage.py                 Session usage display + startup banner
  agent.py                 Function-calling agent loop (Groq tool-calling API)
  tools.py                 Tool execution: read_file, list_dir, run_bash (text-tag based)
  file_utils.py            Shared file-reading helper used by tools.py
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

| Category  | Pipeline                 | Chain (config.py) |
|-----------|---------------------------|---------------------|
| `chat`    | single stage              | `CHAIN_CHAT`        |
| `quick`   | single stage               | `CHAIN_QUICK`       |
| `code`    | Spec → Arch → Build → Review (short: just Build) | `CHAIN_SPEC`/`CHAIN_ARCH`/`CHAIN_BUILD`/`CHAIN_REVIEW` |
| `write`   | Draft → Final              | `CHAIN_DRAFT`/`CHAIN_FINAL` |
| `analyze` | Analysis → Deeper           | `CHAIN_ANALYZE`     |

Every `CHAIN_*` constant now contains **all 9 providers** (a curated preferred prefix, then the rest of `ALL_PROVIDERS` appended) — see `config._full_chain()`. This is deliberate: previously DeepSeek, Mistral, Gemini, OpenRouter, and Charm Hyper weren't members of any chain at all, regardless of key configuration, making them permanently unreachable. Actual usability of a provider in a given call is now decided entirely at call time (see below), not by chain membership.

### Provider flow (`orchestrator.run_stage` → `try_chain`)

1. **Live filtering** (new in v2.2), applied to the chain list before anything else:
   - drop providers disabled via `/providers` (`provider_settings.is_disabled`)
   - drop providers with no key currently in `os.environ` (`provider_settings.has_configured_key` — checked live, not against the `CONFIGURED_PROVIDERS` import-time snapshot)
   - drop providers disabled for *this specific chain* via `/models` (`chain_settings.filter_chain`), identified by `id()`-matching the chain list against `config.CHAIN_REGISTRY`
   - drop providers already marked depleted this session (existing behavior)
   - each filtering step has a non-empty fallback so a user misconfiguration never fully empties the chain
2. Sort remaining providers by least-used (token counts from state)
3. Apply minute-offset rotation to avoid always hitting the same provider
4. For each provider: call function → handle typed exceptions → check HTTP status → parse response
5. On 401/403/429/402: mark provider as depleted in state, skip future
6. On 5xx or connection error: try next provider
7. Return first successful `(provider_name, content)`

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

`providers.py` raises typed exceptions from `call()` and from parser functions, all with null/type checks before indexing into the response (no more bare `data["choices"][0]["message"]["content"]` without guards).
`orchestrator.py` catches them separately to decide whether to deplete or just skip.

### Live API keys

`providers.py` no longer imports key constants at module load time. Every provider function calls a local `_key(env_var)` → `os.getenv(env_var)` at call time. This means `provider_settings.set_key()` (driven by `/providers`) writing into `os.environ` takes effect on the very next request — no process restart needed. Keep this pattern for any new provider you add; importing `from config import MY_KEY` directly would silently break live key updates.

### Sandboxed code execution (new in v2.2)

`code_utils.try_run()`/`install_deps()` take `sandbox: bool` (default `False`, controlled by `/settings` → "Sandbox code execution") and `auto_run: bool` (default `False`).

- **Unsandboxed** (default): unchanged legacy behavior — `subprocess.run(cmd, shell=True, ...)`, 60s timeout.
- **Sandboxed, POSIX**: no shell (`shlex.split` → argv list), restricted env (`SANDBOX_ENV` — no inherited API keys, `HOME=/tmp`), `resource.setrlimit` for CPU/memory/file-size/core-dump/process-count via `preexec_fn`, 15s wall-clock timeout.
- **Sandboxed, Windows**: `win_sandbox.py` implements a real Job Object via ctypes against `kernel32` directly (`JOB_OBJECT_LIMIT_PROCESS_TIME`, `_PROCESS_MEMORY`, `_ACTIVE_PROCESS`) — no pywin32 dependency. Known limitation: small race window between `Popen()` returning and job assignment (would need suspended-create + `ResumeThread` to close fully; judged acceptable for this tool's "review what you're about to run" threat model).
- If neither backend is available on the current platform, sandbox silently falls back to unsandboxed with a `[warn]` printed — it never just fails the run.
- `install_deps()` (pip/npm) is **never** run through the sandbox's restricted env even when `sandbox=True`, since installs genuinely need network + real `PATH`.

### State files (all in `~`)

| File                      | Contents                                    |
|---------------------------|----------------------------------------------|
| `~/.leverage_ai.env`       | API keys (never committed)                  |
| `~/.leverage_usage.json`   | Token counts, depletion list, daily reset    |
| `~/.leverage_memory.json`  | Stored facts and preferences                 |
| `~/.leverage_convo.json`   | Last 20 conversation turns                   |
| `~/.leverage_settings.json`| `/settings` toggles                          |
| `~/.leverage_providers.json`| `/providers` disabled list + key overrides |
| `~/.leverage_chains.json`  | `/models` per-chain provider disables        |
| `~/.leverage_cache/`       | MD5-keyed exact cache + semantic cache JSON + FastEmbed model cache |
| `~/ai_output/`             | Saved generated code files                   |

## Key Patterns

### Adding a new provider

1. Add API key env var lookup as a local `_key("MY_API_KEY")` call inside the new function in `providers.py` (NOT a module-level constant — see "Live API keys" above)
2. Add function + parser to `providers.py`, with null/type-checked parsing; raise `ProviderAuthError` if no key
3. Add entry to `PROVIDERS` dict in `providers.py`
4. Add name to `ALL_PROVIDERS` list in `config.py` — it will automatically be appended to every `CHAIN_*` via `_full_chain()`, so no per-chain edits needed unless you want it in the curated prefix
5. Add its env var to `provider_settings.PROVIDER_ENV_VARS` so `/providers` can show/set its key

### Adding a new pipeline type

1. Add new `CHAIN_*` list in `config.py` via `_full_chain([...preferred order...])`, and add it to `CHAIN_REGISTRY`
2. Add `pipeline_foo()` in `pipelines.py`
3. Add keyword classifier branch in `orchestrator.py`'s `classify()`
4. Add dispatch case in `__main__.py`'s main loop

### Adding a new `/settings` toggle

Add one entry to `settings.SETTINGS_SCHEMA` (key → `(default, label, description)`). The panel, persistence, and toggle-by-index all work automatically — no other code changes needed unless the setting needs to actually be read somewhere (e.g. `pipeline_code` reading `settings.get("sandbox_code")`).

## Gotchas

- **`python-dotenv` required**: `config.py` uses `load_dotenv()`. Run `pip install -r requirements.txt` first.
- **No hardcoded account IDs**: `CF_ACCOUNT_ID` must be set in env — no fallback.
- **Sandboxing is opt-in, not a security boundary by default**: even sandboxed, this is resource-limiting for accidental runaway scripts, not isolation against an adversarial payload — there's no filesystem jail or network isolation either mode.
- **`agent.py`'s tool-calling is separate from `tools.py`'s tag-based tools** — `tools.py`'s `[[BASH: ...]]`/`[[READ_FILE: ...]]` tag scanning is the older approach; `agent.py` replaces it with real structured tool calling against Groq specifically (`llama-3.3-70b-versatile`) for better instruction-following on tool use. Both currently coexist; check which path a given entry point in `__main__.py` actually uses before assuming the other applies.
- **Cache collisions**: exact-match cache key is MD5 of `prompt + max_tokens`. Semantic cache (FastEmbed, `BAAI/bge-small-en-v1.5`) matches at 0.85 cosine similarity, scoped to entries with the same `max_tokens`.
- **Depletion resets**: only Cloudflare auto-clears on daily reset. Others stay depleted until you delete `~/.leverage_usage.json`.
- **`usage_log` is a module global**: `usage.py` imports it from `orchestrator.py` — avoid reimporting or you'll get a separate list.
- **Chain identity matters for `/models`**: per-chain filtering matches a `provider_chain` argument against `CHAIN_REGISTRY` by `id()`, not by value. If you ever build a chain dynamically (e.g. `list(CHAIN_BUILD)`) instead of passing the `config.py` constant directly, `/models` won't recognize it as that chain.
