import os
from pathlib import Path

def get_file_content(filepath: str) -> str:
    # Allows reading from any path on your system
    path = Path(filepath).expanduser().resolve()
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")
        return f"Error: {filepath} is not a valid file."
    except Exception as e:
        return f"Error reading file: {e}"
