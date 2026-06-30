# Leverage AI v2.2

A multi-provider AI orchestrator for the terminal. It routes requests across 9 free/cheap LLM providers (Groq, Cloudflare, Charm Hyper, OpenRouter, Qwen, Gemini, DeepSeek, Mistral, HuggingFace) with fallback chains, exact + semantic caching, persistent memory, and a real function-calling agent mode — and lets you reconfigure all of it live, mid-session, through `/settings`, `/providers`, and `/models`.

Built and run primarily inside Termux/proot on Android (ARM64), but works anywhere with Python 3.9+.

## Installation

```bash
cp .env.example ~/.leverage_ai.env
# edit ~/.leverage_ai.env and add at least one API key
pip install -e .
```

Or just install dependencies without the editable install:
```bash
pip install -r requirements.txt
```

**Free/cheap API keys**, if you need them:
- [Groq](https://console.groq.com) — fast, generous free tier
- [Cloudflare Workers AI](https://dash.cloudflare.com) — 10k free requests/day (needs both an API token and account ID)
- [OpenRouter](https://openrouter.ai) — aggregator with free models (also covers Qwen)
- [HuggingFace](https://huggingface.co/settings/tokens) — free inference API
- Charm Hyper, Google Gemini, DeepSeek, Mistral also supported

Only **one** key is required to start. Providers without a key are automatically skipped — and you can add a key later, live, via `/providers` without restarting.

## Usage

```bash
python -m leverage_ai
# or, after pip install -e .
leverage-ai
```

Flags:
```
--noexec, -n   Skip running saved code files
--debug, -d    Enable debug logging
--help, -h     Show help
```

### In-app commands

```
remember X       Store a fact or preference
forget X         Remove mentions of X from memory
show memory      Display all stored memories
clear memory     Wipe all stored memories
usage            Check API usage and limits
/settings        Sandboxing, auto-run, semantic cache, debug logging toggles
/providers       Enable/disable providers, view/set API keys live
/models          Enable/disable individual providers per pipeline chain
quit / q         Exit
```

`/settings`, `/providers`, and `/models` each open a numbered sub-prompt — type a number to toggle, or `done` to exit back to the main prompt.

#### `/settings`
- **Sandbox code execution** (default OFF) — run AI-generated code without a shell, with restricted env and CPU/memory/process-count limits, instead of `subprocess.run(shell=True)`. POSIX uses `resource` rlimits; Windows uses a real Job Object implementation (`win_sandbox.py`, ctypes-only, no pywin32 dependency).
- **Auto-run generated code** (default OFF) — skip the `[run] y/N` confirmation.
- **Semantic cache** (default ON) — fuzzy-match near-duplicate prompts via embeddings, on top of the exact-match cache.
- **Debug logging** (default OFF) — same as `--debug`.

#### `/providers`
Lists all 9 providers with live enabled/disabled state and a masked key preview. `<n>` toggles a provider off entirely (it's removed from every chain); `key <n> <value>` sets or overrides that provider's API key for the rest of the session (and persists it); `key <n> clear` removes the override.

#### `/models`
Two-level panel: pick a pipeline stage (`spec`, `arch`, `build`, `review`, `draft`, `final`, `analyze`, `quick`, `chat`), then toggle individual providers on/off within just that chain. Useful if, say, you trust DeepSeek for code review but not for quick factual answers.

### Example session
```
> build a Python web scraper
[code]
[chain] Groq → HuggingFace → Cloudflare → ...
✓ Groq 45->215=260
  [run] scraper.py? [y/N] y
  [run:shell] python3 ~/ai_output/scraper.py
  [ok]
...

> /providers
──────────────────────────────────────────
PROVIDERS
──────────────────────────────────────────
  1. Groq           [ENABLED ]  key: ****gsk_a1b2  (GROQ_API_KEY)
  2. Cloudflare      [DISABLED]  key: (not set)  (CLOUDFLARE_API_KEY)
  ...
  providers> key 7 sk-my-deepseek-key
  [providers] set DeepSeek key -> ****-key
  providers> done
```

## Configuration

### API keys
Set any of these in `~/.leverage_ai.env` (or override live via `/providers`):
```bash
GROQ_API_KEY=gsk_...
CLOUDFLARE_API_KEY=v1_...
CF_ACCOUNT_ID=...
HYPER_API_KEY=...
OPENROUTER_API_KEY=sk-...
GOOGLE_API_KEY=...
DEEPSEEK_API_KEY=sk-...
MISTRAL_API_KEY=...
HUGGINGFACE_API_KEY=hf_...
```

### Colors
```bash
NO_COLOR=1 python -m leverage_ai      # disable
FORCE_COLOR=1 python -m leverage_ai   # force, e.g. when output is piped
```

### Persisted state files (in `~`)
```
.leverage_ai.env           API keys
.leverage_usage.json       Provider usage / depletion tracking
.leverage_memory.json      Remembered facts/preferences
.leverage_convo.json       Conversation history
.leverage_settings.json    /settings toggles
.leverage_providers.json   /providers enable state + key overrides
.leverage_chains.json      /models per-chain provider toggles
.leverage_cache/           Exact-match + semantic cache, plus FastEmbed model files
ai_output/                 Saved code files from the code pipeline
```

None of these are committed (see `.gitignore`); delete any of them to reset that piece of state.

## Architecture

```
leverage_ai/
  __init__.py            Package init
  __main__.py            Entry point, main loop, panel sub-prompts
  config.py              Env loading, provider chains, chain registry
  exceptions.py          Exception hierarchy (ProviderError, ProviderAuthError, ...)
  colors.py              Terminal color utilities

  providers.py           Provider API wrappers - keys read live via os.getenv()
  orchestrator.py        Routing, classification, retry/backoff, live filtering
  pipelines.py           Task-specific pipelines (chat, code, write, analyze, ...)

  settings.py            /settings store (sandbox, auto-run, cache, debug)
  provider_settings.py   /providers store (enable state, key overrides)
  chain_settings.py      /models store (per-chain provider toggles)
  commands.py            Panel renderers + memory commands

  code_utils.py          Code extraction, saving, sandboxed/unsandboxed execution
  win_sandbox.py         Windows Job Object sandbox backend (ctypes, no extra deps)
  semantic_cache.py      FastEmbed-based fuzzy cache (ONNX runtime, ARM64-safe)
  cache.py               Exact-match cache
  memory.py              Persistent facts/preferences + conversation context scoring
  state.py               Usage/depletion state persistence
  usage.py               Usage reporting

  agent.py               Function-calling agent loop (Groq tool-calling API)
  tools.py               Tool execution: read_file, list_dir, run_bash
  file_utils.py          Shared file-reading helper
```

### How a request flows
1. `__main__.py` reads input, checks for `/settings`, `/providers`, `/models`, or memory commands first.
2. Otherwise `orchestrator.py` classifies the request into a task type and hands off to the matching `pipelines.py` function with one of `config.py`'s named chains (`CHAIN_BUILD`, `CHAIN_CHAT`, etc).
3. `orchestrator.run_stage()` filters that chain live against: globally-disabled providers (`/providers`), missing API keys (checked via `os.getenv()`, not a startup snapshot), per-chain disables (`/models`), and providers already marked depleted this session — then tries each survivor in order with exponential backoff + jitter on transient errors.
4. Caching (`cache.py` exact-match, `semantic_cache.py` fuzzy) sits in front of all of this so repeated/similar prompts skip the network entirely.

### Provider chains are now full candidate pools
Every provider is a real, toggleable member of every chain (curated providers first, rest appended) — previously DeepSeek, Mistral, Gemini, OpenRouter, and Charm Hyper weren't in any chain at all, regardless of keys. `/providers` and `/models` filtering happens live against `os.environ` and the JSON stores above, not against an import-time snapshot, so adding a key or flipping a toggle takes effect on your very next message.

## Common issues

**"No API keys configured"** — set at least one key in `~/.leverage_ai.env`, or via `/providers` once you're in the app.

**"Provider marked as depleted"** — you've hit a quota limit; tracked in `~/.leverage_usage.json`. Delete the file or wait for the provider's reset window.

**"All providers failed"** — check keys with `/providers`, or run with `--debug` for detailed error output.

**Sandboxed code behaves differently than expected** — the sandbox runs without a shell and with a stripped environment (no inherited API keys, `HOME=/tmp`), so scripts relying on shell features (pipes, globbing, env vars) inside the generated code itself may need `auto_run`/non-sandboxed mode instead. This is `/settings` → "Sandbox code execution", off by default.

**Colors not showing** — `FORCE_COLOR=1`, or `NO_COLOR=1` to turn them off deliberately.

## Development

```bash
python -m leverage_ai --debug 2>&1 | grep leverage_ai     # debug logging
python -c "from leverage_ai.config import CONFIGURED_PROVIDERS; print(CONFIGURED_PROVIDERS)"
```

No test suite yet (`pytest` is wired up in `pyproject.toml` for whenever one exists).

## License

MIT
