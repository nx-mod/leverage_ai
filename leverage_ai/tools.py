#!/usr/bin/env python3
"""Real tool execution for Leverage AI: file reading and bash access.

This gives the model actual capabilities instead of letting it improvise
("hallucinate") about having them. Two tools are exposed to the model via
simple tags it can emit in its response:

    [[READ_FILE: path/to/file]]
    [[BASH: some shell command]]

The orchestrator (see __main__.py) scans model output for these tags,
executes them for real, and feeds the result back to the model as a new
turn so it can give a grounded final answer.

Design notes / tradeoffs (read before changing):
- No working-directory pin: bash runs with cwd=$HOME, full access, per
  explicit request. This is NOT a sandbox.
- Commands are classified as "read-only" or "mutating" by a regex
  heuristic (see MUTATING_PATTERNS). This is a convenience guardrail
  against *accidental* destruction, not a security boundary - it can be
  bypassed by an adversarial or sufficiently confused model. Mutating
  commands pause for interactive (y/n) confirmation; read-only ones run
  immediately.
- shell=True is used deliberately (pipes/redirects need to work for this
  to be useful interactively) - again, only acceptable because the user
  has explicitly accepted full-trust risk here.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

# ── Real function-calling schema (Groq/OpenAI-compatible) ──
# Used by agent.py for providers that support structured tool calling.
# The text-tag approach below ([[READ_FILE: ...]] etc.) is kept as a
# fallback path for providers without function-calling support
# (Cloudflare, HuggingFace) - see agent.py for how each is routed.

TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a real file from the local filesystem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Real absolute or ~-relative path to the file, e.g. ~/leverage_ai/README.md",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List the contents of a real directory on the local filesystem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Real absolute or ~-relative directory path, e.g. ~ or ~/leverage_ai",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": (
                "Run a real shell command in the user's home directory. Read-only "
                "commands (ls, cat, git status, grep, find, etc.) run immediately. "
                "Commands that modify or delete anything pause for human confirmation "
                "before running - expect this to sometimes be denied."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "A real, complete shell command, e.g. 'git status' or 'ls -la ~/leverage_ai'",
                    }
                },
                "required": ["command"],
            },
        },
    },
]

# ── Placeholder detection ──
# Small/fast models sometimes echo the literal example text from their
# instructions instead of substituting a real value. Catch placeholder-style
# arguments before hitting the filesystem/shell, so the error fed back to
# the model is instructive ("that's a placeholder, use a real path") rather
# than a generic FileNotFoundError that triggers confused looping.
#
# This is pattern-based rather than an exact-match list, since models
# paraphrase placeholders in many ways: <path>, {path}, [path], path/to/file,
# your_command_here, the file, a filename, etc.

# Bracket/angle/brace wrapped tokens: <path>, {file}, [command], (dirpath)
_BRACKETED_RE = re.compile(r"^[<{\[(].*[>}\])]$")

# Generic "placeholder-shaped" path segments: path/to/X, your/X/here, .../X
_GENERIC_PATH_RE = re.compile(
    r"(^|/)(path|filename|dirpath|directory|file|your[-_]?\w*|some|example|placeholder|"
    r"<\w+>|x|foo|bar)(/|$)",
    re.IGNORECASE,
)

# Bare single words or short phrases that describe a tool generically rather
# than naming a real target. Checked as a whole-string match, not substring,
# so real commands that happen to contain these words (e.g. "ls -la home")
# are NOT flagged.
_GENERIC_WHOLE_PHRASES = {
    "path", "filename", "file", "dirpath", "directory", "shell command",
    "shell", "command", "your_path_here", "path/to/file", "the file",
    "a file", "a command", "your command", "your command here",
    "your_command_here", "filepath", "dir", "the directory",
    "your directory", "n/a", "none", "unknown", "tbd", "todo",
}


def _is_placeholder(arg: str) -> bool:
    a = arg.strip()
    if not a:
        return True
    low = a.lower()
    if low in _GENERIC_WHOLE_PHRASES:
        return True
    if _BRACKETED_RE.match(a):
        return True
    if _GENERIC_PATH_RE.search(low):
        return True
    return False


# ── File reading ──

def get_file_content(filepath: str, max_chars: int = 8000) -> str:
    """Read a real file from disk. No path restriction (full $HOME access)."""
    if _is_placeholder(filepath):
        return (f"Error: '{filepath}' is a placeholder, not a real path. "
                f"Use an actual path like ~/README.md or ~/leverage_ai/README.md.")
    path = Path(filepath).expanduser().resolve()
    try:
        if not path.exists():
            return f"Error: {filepath} does not exist."
        if not path.is_file():
            return f"Error: {filepath} is not a file."
        text = path.read_text(encoding="utf-8", errors="ignore")
        if len(text) > max_chars:
            return text[:max_chars] + f"\n\n...[truncated, {len(text)} chars total]"
        return text
    except Exception as e:
        return f"Error reading file: {e}"


def list_dir(dirpath: str = "~") -> str:
    """List directory contents."""
    if _is_placeholder(dirpath) and dirpath.strip().lower() != "home":
        return (f"Error: '{dirpath}' is a placeholder, not a real path. "
                f"Use an actual path like ~ or ~/leverage_ai.")
    # "home" alone is a common, forgivable miss for "~" - just redirect it
    if dirpath.strip().lower() == "home":
        dirpath = "~"
    path = Path(dirpath).expanduser().resolve()
    try:
        if not path.is_dir():
            return f"Error: {dirpath} is not a directory."
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = []
        for e in entries:
            tag = "/" if e.is_dir() else ""
            lines.append(f"{e.name}{tag}")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {e}"


# ── Bash execution ──

# Heuristic only - see module docstring. Not exhaustive, not a security
# boundary. Order matters: checked top to bottom, first match wins.
MUTATING_PATTERNS = [
    r"\brm\b", r"\bmv\b", r"\bdd\b", r"\bmkfs\b", r"\bshred\b",
    r"\bchmod\b", r"\bchown\b",
    r">>?(?!\s*&)",                      # redirects (but not >&2 style alone)
    r"\bgit\s+(push|commit|reset|clean|checkout\s+--\s)",
    r"\bpip\d?\s+(install|uninstall)\b",
    r"\b(apt|apt-get|dpkg|pacman)\b.*\b(install|remove|purge|-S|-R)\b",
    r"\|\s*(sh|bash|zsh)\b",             # curl ... | sh
    r"\bcurl\b.*-o\b", r"\bwget\b",
    r"\bkill\b", r"\bsystemctl\b",
    r"\btruncate\b", r"\b:>",
    r"\bsed\s+-i\b",
    r"\bcp\b.*-f\b",
]

_MUTATING_RE = re.compile("|".join(MUTATING_PATTERNS), re.IGNORECASE)


def classify_command(cmd: str) -> str:
    """Return 'mutating' or 'read-only' based on heuristic pattern match."""
    return "mutating" if _MUTATING_RE.search(cmd) else "read-only"


def run_bash(cmd: str, confirm_fn=None, timeout: int = 30) -> Tuple[bool, str]:
    """Execute a bash command against the real environment.

    confirm_fn: callable(cmd: str) -> bool. Called only for mutating
    commands. If None, mutating commands are refused outright (safe
    default for non-interactive callers).

    Returns (executed: bool, output: str).
    """
    if _is_placeholder(cmd):
        return False, (f"Error: '{cmd}' is a placeholder, not a real command. "
                        f"Use an actual shell command like 'git status' or 'ls ~'.")

    kind = classify_command(cmd)

    if kind == "mutating":
        if confirm_fn is None or not confirm_fn(cmd):
            return False, f"[skipped - mutating command not confirmed]: {cmd}"

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=os.path.expanduser("~"),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout or ""
        err = result.stderr or ""
        combined = out
        if err:
            combined += f"\n[stderr]\n{err}"
        if result.returncode != 0:
            combined += f"\n[exit code {result.returncode}]"
        if len(combined) > 6000:
            combined = combined[:6000] + "\n...[truncated]"
        return True, combined.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return False, f"[error] command timed out after {timeout}s"
    except Exception as e:
        return False, f"[error] {e}"


# ── Tag parsing ──

READ_FILE_RE = re.compile(r"\[\[READ_FILE:\s*(.+?)\]\]", re.IGNORECASE)
LIST_DIR_RE = re.compile(r"\[\[LIST_DIR:\s*(.+?)\]\]", re.IGNORECASE)
BASH_RE = re.compile(r"\[\[BASH:\s*(.+?)\]\]", re.IGNORECASE | re.DOTALL)

_ALL_TAG_PATTERNS = [
    ("READ_FILE", READ_FILE_RE),
    ("LIST_DIR", LIST_DIR_RE),
    ("BASH", BASH_RE),
]


def extract_tool_call(text: str) -> Optional[Tuple[str, str]]:
    """Find the tool-call tag that appears FIRST in the text (by position,
    not by a fixed READ_FILE > LIST_DIR > BASH priority - a model that
    writes [[BASH: ...]] before any other tag means BASH, not whichever
    tag happens to be checked first in code).

    If more than one tag is present, only the earliest one is acted on -
    the model was told one tag per reply, so extra tags are dropped
    silently here, but see also tools.py's count_tool_tags() which the
    caller can use to detect this and warn the model explicitly.
    """
    matches = []
    for name, pattern in _ALL_TAG_PATTERNS:
        m = pattern.search(text)
        if m:
            matches.append((m.start(), name, m.group(1).strip()))
    if not matches:
        return None
    matches.sort(key=lambda t: t[0])
    _, name, arg = matches[0]
    return (name, arg)


def count_tool_tags(text: str) -> int:
    """Count how many tool-call tags appear in the text, so callers can
    tell the model when it violated the one-tag-per-reply rule instead of
    silently dropping the extras.
    """
    return sum(1 for _, pattern in _ALL_TAG_PATTERNS for _ in pattern.finditer(text))
