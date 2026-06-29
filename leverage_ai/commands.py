#!/usr/bin/env python3
"""Interactive command handlers for Leverage AI."""

from leverage_ai.memory import load_memory, save_memory, add_memory
from leverage_ai.state import load_state

def handle_memory_command(idea, mem):
    """Handle memory commands like 'remember X' or 'forget X'."""
    lower = idea.lower()
    if lower.startswith("remember "):
        fact = idea[9:].strip()
        add_memory(mem, "facts", fact)
        print(f"  [memory] remembered: {fact}")
        return True
    elif lower.startswith("forget "):
        target = idea[7:].strip().lower()
        for cat in ["facts", "preferences"]:
            mem[cat] = [item for item in mem.get(cat, []) if target not in item["text"].lower()]
        save_memory(mem)
        print(f"  [memory] forgot mentions of: {target}")
        return True
    elif lower == "show memory":
        print("\n  [MEMORY]")
        for cat in ["facts", "preferences"]:
            items = mem.get(cat, [])
            if items:
                print(f"  {cat.upper()} ({len(items)} items):")
                for item in items[-5:]:
                    print(f"    - {item['text']}")
        return True
    elif lower.startswith("clear memory"):
        mem.clear()
        save_memory(mem)
        print("  [memory] all memory cleared")
        return True
    elif lower == "usage":
        print("\n  [USAGE STATUS]")
        state = load_state()

        cf_req = state.get("cf_req", 0)
        cf_pct = (cf_req / 10000) * 100
        print(f"  Cloudflare: {cf_req:,}/10,000 requests ({cf_pct:.1f}%) - resets daily")

        groq_tokens = sum(v for k, v in state.get("tokens", {}).items() if k.startswith("Groq"))
        groq_pct = (groq_tokens / 500000) * 100
        print(f"  Groq: {groq_tokens:,}/500,000 tokens ({groq_pct:.1f}%) - rolling 24h")

        depleted = state.get("depleted", [])
        if depleted:
            print(f"  Depleted: {', '.join(depleted)}")
        else:
            print(f"  All providers available")

        return True
    return False
