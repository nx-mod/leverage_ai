#!/usr/bin/env python3
"""Code extraction, saving, running, and dependency management."""

import re
import subprocess
from leverage_ai.config import WORK_DIR, LANG_MAP

def extract_code(text):
    """Extract code blocks from markdown-style responses."""
    blocks = re.findall(r"```(\w+)?\n(.*?)```", text, re.DOTALL)
    return [((lang or "txt").strip(), code.strip()) for lang, code in blocks]

def save_code(blocks, idea):
    """Save extracted code blocks to files."""
    if not blocks:
        return []
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", idea.lower().strip())[:30].strip("_")
    paths = []
    for i, (lang, code) in enumerate(blocks):
        ext = LANG_MAP.get(lang, {}).get("ext", lang or "txt")
        name = f"{slug}_{i}.{ext}" if i else f"{slug}.{ext}"
        p = WORK_DIR / name
        p.write_text(code)
        paths.append(p)
    return paths

def try_run(paths, idea, noexec=False):
    """Offer to run saved code files."""
    if not paths:
        return
    if noexec:
        print("  [skip] --noexec")
        return
    main = paths[0]
    ext = main.suffix.lstrip(".")
    cfg = next((c for c in LANG_MAP.values() if c["ext"] == ext), None)
    if not cfg:
        print(f"  [skip] no runner for .{ext}")
        return
    ans = input(f"  [run] {main.name}? [y/N] ").strip().lower()
    if ans not in ("y", "yes"):
        print(f"  [skip] {main.name}")
        return
    cmd = cfg["run"].replace("{path}", str(main))
    print(f"  [run] {cmd}")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            out = r.stdout.strip()
            if out:
                print(f"  [ok]\n{out[:800]}")
            else:
                print("  [ok] (no output)")
        else:
            err = r.stderr.strip()[:400]
            print(f"  [exit {r.returncode}] {err}")
    except subprocess.TimeoutExpired:
        print("  [timeout] killed after 60s")
    except Exception as e:
        print(f"  [error] {e}")

def install_deps(paths):
    """Install dependencies from requirements.txt or package.json."""
    for p in paths:
        name = p.name
        if name == "requirements.txt":
            ans = input("  [deps] pip install? [y/N] ").strip().lower()
            if ans in ("y", "yes"):
                subprocess.run(f"pip install -r {p}", shell=True, capture_output=True, text=True, timeout=120)
                print("  [deps] done")
        elif name == "package.json":
            ans = input("  [deps] npm install? [y/N] ").strip().lower()
            if ans in ("y", "yes"):
                subprocess.run("npm install", shell=True, capture_output=True, text=True, timeout=120, cwd=p.parent)
                print("  [deps] done")

def show_files(paths):
    """Display saved file info."""
    if not paths:
        return
    total = sum(p.stat().st_size for p in paths if p.exists())
    print(f"  [files] {len(paths)} file(s), {total:,} bytes in {WORK_DIR}")

def compress_prompt(prompt, max_tokens):
    """Compress prompt by removing redundant content while preserving meaning."""
    if len(prompt.split()) <= max_tokens * 0.8:
        return prompt

    lines = prompt.split("\n")
    compressed = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if len(line.split()) <= 20:
            compressed.append(line)
        else:
            words = line.split()
            if len(words) > 50:
                compressed.append(" ".join(words[:50]) + "...")
            else:
                compressed.append(line)

    return "\n".join(compressed)
