#!/usr/bin/env python3
"""Usage tracking and cost reporting for Leverage AI."""

import time
from leverage_ai.config import COSTS, LIMITS, CACHE_DIR
from leverage_ai.state import save_state
from leverage_ai.orchestrator import usage_log

def show_usage(state):
    """Display session usage, costs, and provider status."""
    if not usage_log:
        return

    today = time.strftime("%Y-%m-%d")
    if state["day"] != today:
        state["day"] = today
        state["cf_req"] = 0
        state["tokens"] = {}
        state["depleted"] = [p for p in state.get("depleted", []) if p != "Cloudflare"]

    print("\n" + "=" * 55)
    print("USAGE")
    print("=" * 55)
    total_tok = 0
    total_cost = 0
    cache_hits = 0
    cf_req = 0

    for prov, model, u in usage_log:
        if not isinstance(u, dict):
            continue

        if prov == "Cache":
            cache_hits += 1
            continue

        pt = u.get("prompt_tokens", 0) or 0
        ct = u.get("completion_tokens", 0) or 0
        tt = u.get("total_tokens", pt + ct) or (pt + ct)
        total_tok += tt

        # Check usage limits
        if prov in LIMITS:
            lim = LIMITS[prov]
            if lim["type"] == "requests" and prov == "Cloudflare":
                pct = (state.get("cf_req", 0) / lim["limit"]) * 100
                if pct > 80:
                    print(f"  [warn] {prov}: {state.get('cf_req', 0):,}/{lim['limit']:,} requests ({pct:.0f}%)")
            elif lim["type"] == "tokens":
                groq_tokens = sum(v for k, v in state.get("tokens", {}).items() if k.startswith("Groq"))
                pct = (groq_tokens / lim["limit"]) * 100
                if pct > 80:
                    print(f"  [warn] {prov}: {groq_tokens:,}/{lim['limit']:,} tokens ({pct:.0f}%)")

        cost_per_m = COSTS.get(prov, 0)
        est_cost = (tt / 1_000_000) * cost_per_m
        total_cost += est_cost

        cost = u.get("cost", {})
        if isinstance(cost, dict):
            hc = cost.get("hypercredits", 0)
            usd = cost.get("usd", 0)
        else:
            hc = 0
            usd = cost or u.get("total_cost", 0) or 0
        hc_s = f" {hc}HC" if hc else ""
        cost_display = f"${usd:.6f}" if usd > 0 else f"~${est_cost:.6f}"
        print(f"  {prov:14s} {tt:>5d} tok  {cost_display}{hc_s}")

        key = f"{prov}/{model}"
        state["tokens"][key] = state["tokens"].get(key, 0) + tt
        if prov == "Cloudflare":
            cf_req += 1

    state["cf_req"] += cf_req
    save_state(state)

    sep = "-" * 40
    print(f"  {sep}")
    print(f"  {'SESSION':14s} {total_tok:>5d} tok  ~${total_cost:.6f}")
    if cache_hits > 0:
        print(f"  {'CACHE HITS':14s} {cache_hits} response(s)")
    cum = sum(state["tokens"].values())
    print(f"  {'CUMULATIVE':14s} {cum:>5d} tok")

    session_count = len([u for u in usage_log if u[0] != "Cache"])
    if session_count > 0:
        avg_tok = total_tok / session_count
        print(f"  {'AVG/REQUEST':14s} {avg_tok:.0f} tok")

    depleted = state.get("depleted", [])
    if depleted:
        print(f"  {'DEPLETED':14s} {', '.join(depleted)}")

    expensive_rate = 2.00
    would_cost = (total_tok / 1_000_000) * expensive_rate
    saved = would_cost - total_cost
    if saved > 0:
        print(f"  {'ESTIMATED SAVINGS':14s} ~${saved:.6f} vs premium models")

def banner(state, noexec=False):
    """Display startup banner with provider status."""
    dep = state.get("depleted", [])
    alive = [p for p in ["Cloudflare", "Groq", "Charm Hyper", "OpenRouter", "Qwen",
                         "HuggingFace", "Gemini", "DeepSeek", "Mistral"] if p not in dep]
    tags = [f"{p} x" for p in dep]
    dep_s = f"  depleted: {', '.join(tags)}" if tags else ""
    noexec_s = "  [noexec]" if noexec else ""

    cache_files = list(CACHE_DIR.glob("*.json")) if CACHE_DIR.exists() else []
    cache_size = sum(f.stat().st_size for f in cache_files) if cache_files else 0
    cache_s = f"  cache: {len(cache_files)} responses ({cache_size:,} bytes)" if cache_files else ""

    print(f"\n{'='*60}")
    print(f"  Leverage AI v2.0 - Multi-Provider Assistant")
    print(f"{'='*60}")
    print(f"  Providers: {' | '.join(alive)}{dep_s}")
    print(f"  {cache_s}{noexec_s}")
    print(f"\n  Type your question or use commands:")
    print(f"    remember X   - Store information")
    print(f"    forget X     - Remove from memory")
    print(f"    show memory  - View stored info")
    print(f"    usage        - Check API limits")
    print(f"    clear memory - Reset all memory")
    print(f"    quit/q       - Exit")
    print(f"{'='*60}")
