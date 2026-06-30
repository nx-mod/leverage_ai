#!/usr/bin/env python3
"""Code extraction, saving, running, and dependency management.

Execution has two modes, controlled by the `sandbox_code` setting
(see settings.py, default OFF):

  - sandbox_code=False (default): identical to existing behavior -
    subprocess.run(cmd, shell=True, ...). No change for anyone who
    hasn't opted in.
  - sandbox_code=True: runs without a shell (argv list, no string
    interpolation through /bin/sh), with a stripped-down environment,
    a dedicated cwd, and CPU/memory/file-size resource limits applied
    via the `resource` module (POSIX only - falls back to the
    unsandboxed path with a warning on platforms without `resource`,
    e.g. native Windows; Termux/Linux/macOS all have it).
"""

import re
import shlex
import subprocess
import sys
from leverage_ai.config import WORK_DIR, LANG_MAP

try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    from leverage_ai.win_sandbox import create_limited_job, assign_process_to_job, close_job
    HAS_WIN_SANDBOX = True
else:
    HAS_WIN_SANDBOX = False

# Sandbox limits
SANDBOX_CPU_SECONDS = 10
SANDBOX_MEM_BYTES = 256 * 1024 * 1024   # 256MB address space
SANDBOX_FSIZE_BYTES = 10 * 1024 * 1024  # 10MB max file write
SANDBOX_TIMEOUT = 15                    # wall-clock seconds (tighter than normal 60s)
NORMAL_TIMEOUT = 60

# Minimal env passed to sandboxed children - no inherited API keys, no
# inherited PATH extras, just enough to find interpreters.
SANDBOX_ENV = {
    "PATH": "/usr/bin:/bin:/usr/local/bin",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
}


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


def _sandbox_preexec():
    """Run in the child right after fork(), before exec(). POSIX only."""
    if not HAS_RESOURCE:
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (SANDBOX_CPU_SECONDS, SANDBOX_CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_AS, (SANDBOX_MEM_BYTES, SANDBOX_MEM_BYTES))
        resource.setrlimit(resource.RLIMIT_FSIZE, (SANDBOX_FSIZE_BYTES, SANDBOX_FSIZE_BYTES))
        # Disallow core dumps and limit number of processes/threads the
        # child can spawn, where the platform supports it.
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if hasattr(resource, "RLIMIT_NPROC"):
            resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    except (ValueError, OSError):
        # Some limits aren't adjustable on some platforms/containers
        # (e.g. already below the requested ceiling) - don't block execution.
        pass


def _run_cmd(cmd_str, cwd=None, sandbox=False, timeout=None):
    """Run a command, either via shell (legacy) or as a sandboxed argv list."""
    if not sandbox:
        return subprocess.run(
            cmd_str, shell=True, capture_output=True, text=True,
            timeout=timeout or NORMAL_TIMEOUT, cwd=cwd,
        )

    # Sandboxed path: no shell. shlex.split avoids shell metacharacter
    # interpretation entirely - "{path}" substitution already happened
    # before this point, so this just tokenizes the resulting argv.
    argv = shlex.split(cmd_str)
    timeout = timeout or SANDBOX_TIMEOUT

    if IS_WINDOWS and HAS_WIN_SANDBOX:
        return _run_cmd_windows_sandboxed(argv, cwd, timeout)

    kwargs = dict(
        capture_output=True, text=True, timeout=timeout,
        cwd=cwd, env=SANDBOX_ENV,
    )
    if HAS_RESOURCE:
        kwargs["preexec_fn"] = _sandbox_preexec
    return subprocess.run(argv, **kwargs)


def _run_cmd_windows_sandboxed(argv, cwd, timeout):
    """Run argv under a resource-limited Job Object (see win_sandbox.py)."""
    job = create_limited_job(SANDBOX_CPU_SECONDS, SANDBOX_MEM_BYTES, max_processes=8)

    proc = subprocess.Popen(
        argv, cwd=cwd, env=SANDBOX_ENV,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )

    if job:
        assign_process_to_job(job, proc.pid)

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        close_job(job)
        raise
    finally:
        close_job(job)

    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def try_run(paths, idea, noexec=False, sandbox=False, auto_run=False):
    """Offer to run saved code files.

    sandbox: if True, run without a shell and with resource limits
             (see _run_cmd / _sandbox_preexec). Default False = unchanged
             legacy behavior.
    auto_run: if True, skip the y/N confirmation prompt.
    """
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

    if not auto_run:
        ans = input(f"  [run] {main.name}? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print(f"  [skip] {main.name}")
            return

    cmd = cfg["run"].replace("{path}", str(main))
    mode = "sandboxed" if sandbox else "shell"
    print(f"  [run:{mode}] {cmd}")

    if sandbox and not HAS_RESOURCE and not (IS_WINDOWS and HAS_WIN_SANDBOX):
        print("  [warn] no sandboxing backend available on this platform; running unsandboxed")
        sandbox = False

    try:
        r = _run_cmd(cmd, sandbox=sandbox)
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
        limit = SANDBOX_TIMEOUT if sandbox else NORMAL_TIMEOUT
        print(f"  [timeout] killed after {limit}s")
    except Exception as e:
        print(f"  [error] {e}")


def install_deps(paths, sandbox=False, auto_run=False):
    """Install dependencies from requirements.txt or package.json.

    Dependency installation always needs network + real PATH, so it is
    NOT run through the sandbox's restricted env even when sandbox=True -
    sandboxing here would just break installs. sandbox/auto_run are
    accepted for signature symmetry but only auto_run is honored.
    """
    for p in paths:
        name = p.name
        if name == "requirements.txt":
            if auto_run or input("  [deps] pip install? [y/N] ").strip().lower() in ("y", "yes"):
                subprocess.run(f"pip install -r {p}", shell=True, capture_output=True, text=True, timeout=120)
                print("  [deps] done")
        elif name == "package.json":
            if auto_run or input("  [deps] npm install? [y/N] ").strip().lower() in ("y", "yes"):
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
