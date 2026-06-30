from leverage_ai.file_utils import get_file_content
#!/usr/bin/env python3
"""Interactive command handlers for Leverage AI."""

from leverage_ai.memory import load_memory, save_memory, add_memory
from leverage_ai.state import load_state
from leverage_ai.settings import (
    render_panel, key_for_index, toggle_setting, SETTINGS_SCHEMA,
)
from leverage_ai.provider_settings import (
    ALL_PROVIDER_NAMES, PROVIDER_ENV_VARS, EXTRA_ENV_VARS,
    is_disabled as provider_is_disabled, toggle_provider, set_key, clear_key,
    get_key_display,
)
from leverage_ai.chain_settings import (
    is_disabled_in_chain, toggle_provider_in_chain,
)
from leverage_ai.config import CHAIN_REGISTRY


def handle_settings_command(idea, settings):
    """Handle the /settings panel: '/settings', '/settings 2', '/settings done'.

    Returns True if the input was a settings command (and handled it),
    False otherwise. Caller should keep calling this in a sub-loop while
    it returns True and the panel is "open" - see __main__.py.
    """
    lower = idea.strip().lower()
    if lower == "/settings":
        print(render_panel(settings))
        return True
    if lower in ("done", "exit", "back", "q"):
        return False
    if lower.isdigit():
        try:
            key = key_for_index(int(lower))
        except IndexError:
            print(f"  [settings] no option {lower}")
            return True
        new_val = toggle_setting(settings, key)
        label = SETTINGS_SCHEMA[key][1]
        state_str = "ON" if new_val else "OFF"
        print(f"  [settings] {label} -> {state_str}")
        print(render_panel(settings))
        return True
    print("  [settings] type a number to toggle, or 'done' to exit")
    return True


def _render_providers_panel(provider_settings):
    import os
    from leverage_ai.colors import section, success, muted, info
    from leverage_ai.provider_settings import mask_key

    lines = [f"\n{section('─' * 60)}", f"{section('PROVIDERS')}", f"{section('─' * 60)}"]
    for i, name in enumerate(ALL_PROVIDER_NAMES, start=1):
        enabled = not provider_is_disabled(provider_settings, name)
        state_str = success("ENABLED ") if enabled else muted("DISABLED")
        key_str = get_key_display(name)
        env_var = PROVIDER_ENV_VARS.get(name, "")
        lines.append(f"  {i}. {name:<14} [{state_str}]  key: {key_str}  ({env_var})")
        for extra_label, extra_var in EXTRA_ENV_VARS.get(name, []):
            lines.append(f"      + {extra_label}: {mask_key(os.environ.get(extra_var))} ({extra_var})")
    lines.append(f"{section('─' * 60)}")
    lines.append(info("  <n>            toggle provider on/off"))
    lines.append(info("  key <n> <val>  set/override API key for provider n"))
    lines.append(info("  key <n> clear  remove key override (env var still applies)"))
    lines.append(info("  done           exit"))
    return "\n".join(lines)


def handle_providers_command(idea, provider_settings):
    """Handle the /providers panel."""
    lower = idea.strip().lower()
    raw = idea.strip()

    if lower == "/providers":
        print(_render_providers_panel(provider_settings))
        return True
    if lower in ("done", "exit", "back", "q"):
        return False

    if lower.isdigit():
        n = int(lower)
        if not (1 <= n <= len(ALL_PROVIDER_NAMES)):
            print(f"  [providers] no provider {n}")
            return True
        name = ALL_PROVIDER_NAMES[n - 1]
        enabled = toggle_provider(provider_settings, name)
        print(f"  [providers] {name} -> {'ENABLED' if enabled else 'DISABLED'}")
        print(_render_providers_panel(provider_settings))
        return True

    parts = raw.split(None, 2)
    if len(parts) >= 2 and parts[0].lower() == "key":
        try:
            n = int(parts[1])
        except ValueError:
            print("  [providers] usage: key <n> <value>  OR  key <n> clear")
            return True
        if not (1 <= n <= len(ALL_PROVIDER_NAMES)):
            print(f"  [providers] no provider {n}")
            return True
        name = ALL_PROVIDER_NAMES[n - 1]
        env_var = PROVIDER_ENV_VARS.get(name)
        if not env_var:
            print(f"  [providers] {name} doesn't take a key")
            return True
        if len(parts) == 2 or parts[2].lower() == "clear":
            clear_key(provider_settings, env_var)
            print(f"  [providers] cleared override for {name} ({env_var})")
        else:
            value = parts[2]
            set_key(provider_settings, env_var, value)
            print(f"  [providers] set {name} key -> {get_key_display(name)}")
        print(_render_providers_panel(provider_settings))
        return True

    print("  [providers] type a number to toggle, 'key <n> <value>' to set a key, or 'done' to exit")
    return True


def _render_models_chain_list():
    from leverage_ai.colors import section, info

    lines = [f"\n{section('─' * 60)}", f"{section('MODELS / CHAINS')}", f"{section('─' * 60)}"]
    for i, name in enumerate(CHAIN_REGISTRY.keys(), start=1):
        lines.append(f"  {i}. {name}")
    lines.append(f"{section('─' * 60)}")
    lines.append(info("  <n>    open this chain's provider toggles"))
    lines.append(info("  done   exit"))
    return "\n".join(lines)


def _render_chain_providers_panel(chain_name, chain_settings):
    from leverage_ai.colors import section, success, muted, info

    chain_list = CHAIN_REGISTRY[chain_name]
    lines = [f"\n{section('─' * 60)}", f"{section(f'CHAIN: {chain_name}')}", f"{section('─' * 60)}"]
    for i, name in enumerate(chain_list, start=1):
        enabled = not is_disabled_in_chain(chain_settings, chain_name, name)
        state_str = success("ON ") if enabled else muted("OFF")
        lines.append(f"  {i}. {name:<14} [{state_str}]")
    lines.append(f"{section('─' * 60)}")
    lines.append(info("  <n>    toggle this provider in this chain"))
    lines.append(info("  back   return to chain list"))
    lines.append(info("  done   exit"))
    return "\n".join(lines)


def handle_models_command(idea, chain_settings, models_nav):
    """Handle the /models panel - two-level: pick a chain, then toggle providers in it.

    models_nav is a mutable dict {"chain": None or chain_name} tracking
    which level of the panel we're on, since this needs more state than
    /settings or /providers (which are single-level).

    Returns True if handled and panel should stay open, False to exit.
    """
    lower = idea.strip().lower()

    if lower == "/models":
        models_nav["chain"] = None
        print(_render_models_chain_list())
        return True

    if lower in ("done", "exit", "q"):
        if models_nav.get("chain") is not None:
            models_nav["chain"] = None
            return True
        return False

    if lower == "back":
        if models_nav.get("chain") is not None:
            models_nav["chain"] = None
            print(_render_models_chain_list())
            return True
        return False

    current_chain = models_nav.get("chain")

    if current_chain is None:
        # Top level: picking which chain to open
        if lower.isdigit():
            names = list(CHAIN_REGISTRY.keys())
            n = int(lower)
            if not (1 <= n <= len(names)):
                print(f"  [models] no chain {n}")
                return True
            models_nav["chain"] = names[n - 1]
            print(_render_chain_providers_panel(models_nav["chain"], chain_settings))
            return True
        print("  [models] type a number to open a chain, or 'done' to exit")
        return True

    # Inside a chain: toggling providers in it
    if lower.isdigit():
        chain_list = CHAIN_REGISTRY[current_chain]
        n = int(lower)
        if not (1 <= n <= len(chain_list)):
            print(f"  [models] no provider {n} in chain '{current_chain}'")
            return True
        provider_name = chain_list[n - 1]
        enabled = toggle_provider_in_chain(chain_settings, current_chain, provider_name)
        print(f"  [models] {provider_name} in '{current_chain}' -> {'ON' if enabled else 'OFF'}")
        print(_render_chain_providers_panel(current_chain, chain_settings))
        return True

    print("  [models] type a number to toggle, 'back' for chain list, or 'done' to exit")
    return True


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
