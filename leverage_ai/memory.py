#!/usr/bin/env python3
"""Memory and conversation history management for Leverage AI."""

import json
import time
from leverage_ai.config import MEMORY_FILE, CONVO_FILE

# -- Memory --

def load_memory():
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text())
        except:
            pass
    return {"facts": [], "preferences": [], "context": {}}

def save_memory(mem):
    MEMORY_FILE.write_text(json.dumps(mem, indent=2))

def add_memory(mem, category, item):
    mem.setdefault(category, [])
    mem[category].append({"text": item, "timestamp": time.time()})
    if len(mem[category]) > 100:
        mem[category] = mem[category][-100:]
    save_memory(mem)

def get_relevant_context(mem, query):
    """Enhanced context retrieval with TF-IDF-like scoring."""
    words = set(query.lower().split())
    scored_items = []

    for cat in ["facts", "preferences"]:
        for item in mem.get(cat, []):
            item_words = set(item["text"].lower().split())
            overlap = len(words & item_words) / max(len(words), 1)
            if overlap > 0.2:
                scored_items.append((overlap, item["text"]))

    scored_items.sort(reverse=True, key=lambda x: x[0])
    return [text for _, text in scored_items[:5]]

# -- Conversation History --

def load_conversation():
    if CONVO_FILE.exists():
        try:
            return json.loads(CONVO_FILE.read_text())
        except:
            pass
    return []

def save_conversation(convo):
    if len(convo) > 20:
        convo = convo[-20:]
    CONVO_FILE.write_text(json.dumps(convo, indent=2))

def add_to_conversation(convo, role, content):
    convo.append({"role": role, "content": content, "timestamp": time.time()})
    save_conversation(convo)

def get_conversation_context(convo, max_turns=3):
    """Get recent conversation turns for context."""
    if not convo:
        return ""
    recent = convo[-max_turns*2:]
    lines = []
    for msg in recent:
        prefix = "You" if msg["role"] == "user" else "Assistant"
        lines.append(f"{prefix}: {msg['content'][:200]}")
    return "\n".join(lines) if lines else ""
