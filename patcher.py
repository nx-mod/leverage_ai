path = "leverage_ai/orchestrator.py"
with open(path, "r") as f: content = f.read()

# 1. Add global
if "FAILED_THIS_SESSION = set()" not in content:
    content = content.replace("usage_log: List[Tuple[str, str, Dict[str, Any]]] = []", 
                              "usage_log: List[Tuple[str, str, Dict[str, Any]]] = []\nFAILED_THIS_SESSION = set()")

# 2. Add blacklist check
if "if prov in FAILED_THIS_SESSION:" not in content:
    check = '        if prov in FAILED_THIS_SESSION:\n            continue\n        if prov in state.get("depleted", []):'
    content = content.replace('        if prov in state.get("depleted", []):', check)

# 3. Add error handling
error_line = '            logger.warning(f"{prov}: Connection error - {e}")'
if "FAILED_THIS_SESSION.add(prov)" not in content:
    replacement = error_line + '\n            FAILED_THIS_SESSION.add(prov)\n            print(f"  {provider(prov)} {warn_color(\'Connection error - Blacklisted\')}")'
    content = content.replace(error_line, replacement)

with open(path, "w") as f: f.write(content)
