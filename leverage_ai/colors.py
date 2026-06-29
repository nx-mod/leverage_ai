#!/usr/bin/env python3
"""Terminal color utilities for nice output."""

import sys
import os

# Check if terminal supports colors
NO_COLOR = os.environ.get("NO_COLOR")
FORCE_COLOR = os.environ.get("FORCE_COLOR")
SUPPORTS_COLOR = sys.stdout.isatty() and not NO_COLOR or FORCE_COLOR

# ANSI color codes
class Color:
    # Styles
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    
    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright foreground colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    
    # Background colors
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"


def colored(text: str, color: str, bold: bool = False) -> str:
    """Return colored text if terminal supports it."""
    if not SUPPORTS_COLOR:
        return text
    
    style = Color.BOLD if bold else ""
    return f"{style}{color}{text}{Color.RESET}"


def success(text: str) -> str:
    """Green success message."""
    return colored(text, Color.BRIGHT_GREEN, bold=True)


def error(text: str) -> str:
    """Red error message."""
    return colored(text, Color.BRIGHT_RED, bold=True)


def warning(text: str) -> str:
    """Yellow warning message."""
    return colored(text, Color.BRIGHT_YELLOW, bold=True)


def info(text: str) -> str:
    """Cyan info message."""
    return colored(text, Color.BRIGHT_CYAN)


def provider(text: str) -> str:
    """Blue provider name."""
    return colored(text, Color.BRIGHT_BLUE, bold=True)


def chain(text: str) -> str:
    """Magenta chain indicator."""
    return colored(text, Color.BRIGHT_MAGENTA)


def token_count(text: str) -> str:
    """Green token count."""
    return colored(text, Color.GREEN, bold=True)


def cost(text: str) -> str:
    """Yellow cost indicator."""
    return colored(text, Color.YELLOW)


def header(text: str) -> str:
    """Bold cyan header."""
    return colored(text, Color.BRIGHT_CYAN, bold=True)


def section(text: str) -> str:
    """Bold white section."""
    return colored(text, Color.WHITE, bold=True)


def muted(text: str) -> str:
    """Dim gray text."""
    return colored(text, Color.DIM)


def pipeline_type(name: str) -> str:
    """Color code for pipeline type."""
    colors = {
        "chat": Color.BRIGHT_CYAN,
        "quick": Color.BRIGHT_GREEN,
        "code": Color.BRIGHT_MAGENTA,
        "write": Color.BRIGHT_YELLOW,
        "analyze": Color.BRIGHT_BLUE,
        "memory": Color.BRIGHT_WHITE,
        "usage": Color.YELLOW,
    }
    color = colors.get(name, Color.WHITE)
    return colored(f"[{name}]", color, bold=True)


def spinner_frame(frame_num: int) -> str:
    """Return a spinner frame."""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    return colored(frames[frame_num % len(frames)], Color.BRIGHT_CYAN)
