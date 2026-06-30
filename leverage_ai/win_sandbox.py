#!/usr/bin/env python3
"""Windows-native sandbox limits via Job Objects (ctypes, no extra deps).

POSIX gets RLIMIT_CPU/RLIMIT_AS/etc through the `resource` module
(see code_utils.py's _sandbox_preexec). Windows has no equivalent
module, which is why the original sandbox implementation just fell
back to "unsandboxed" there. Job Objects are the real Windows
analogue: a kernel object you assign a process to that can enforce
- JOB_OBJECT_LIMIT_PROCESS_MEMORY  (~ RLIMIT_AS)
- JOB_OBJECT_LIMIT_PROCESS_TIME    (~ RLIMIT_CPU - kills the process
  when its own CPU time, not wall clock, exceeds the limit)
- JOB_OBJECT_LIMIT_ACTIVE_PROCESS  (~ RLIMIT_NPROC)

This intentionally only depends on ctypes + the stdlib, since adding
pywin32 as a hard dependency would break installs on non-Windows
platforms unless carefully gated, and this is a small enough surface
to implement directly against kernel32.
"""

import ctypes
import logging
import sys
from ctypes import wintypes

logger = logging.getLogger("leverage_ai.win_sandbox")

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    kernel32 = ctypes.windll.kernel32

    # -- Struct definitions (winnt.h) --

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),  # 100-ns units
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JobObjectExtendedLimitInformation = 9

    JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    PROCESS_SET_QUOTA = 0x0100
    PROCESS_TERMINATE = 0x0001


def create_limited_job(cpu_seconds: float, mem_bytes: int, max_processes: int = 8):
    """Create a Job Object with CPU/memory/process-count limits.

    Returns a job handle (HANDLE) on success, or None if anything
    fails - callers should treat None as "couldn't sandbox, proceed
    unsandboxed" rather than raising, since this is a best-effort
    hardening layer, not the only thing standing between the user and
    a malicious script.
    """
    if not IS_WINDOWS:
        return None
    try:
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            logger.debug("CreateJobObjectW failed")
            return None

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.PerProcessUserTimeLimit = int(cpu_seconds * 10_000_000)  # 100ns units
        info.BasicLimitInformation.ActiveProcessLimit = max_processes
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_PROCESS_TIME
            | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        info.ProcessMemoryLimit = mem_bytes

        ok = kernel32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation,
            ctypes.byref(info), ctypes.sizeof(info),
        )
        if not ok:
            logger.debug("SetInformationJobObject failed")
            kernel32.CloseHandle(job)
            return None

        return job
    except Exception as e:
        logger.debug(f"create_limited_job failed: {e}")
        return None


def assign_process_to_job(job, pid: int) -> bool:
    """Assign an already-spawned process (by pid) to a job object.

    There's a small race between Popen() returning and this call where
    the child could do meaningful work unrestricted. For this tool's
    threat model (reviewing/running AI-generated snippets, not
    adversarial red-team payloads) that window is an acceptable
    trade-off against the complexity of spawning suspended + resuming
    after assignment, which needs the full CreateProcess/ResumeThread
    path instead of subprocess.Popen.
    """
    if not IS_WINDOWS or not job:
        return False
    try:
        handle = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not handle:
            logger.debug(f"OpenProcess failed for pid {pid}")
            return False
        ok = kernel32.AssignProcessToJobObject(job, handle)
        kernel32.CloseHandle(handle)
        if not ok:
            logger.debug(f"AssignProcessToJobObject failed for pid {pid}")
            return False
        return True
    except Exception as e:
        logger.debug(f"assign_process_to_job failed: {e}")
        return False


def close_job(job) -> None:
    if IS_WINDOWS and job:
        try:
            kernel32.CloseHandle(job)
        except Exception:
            pass
