#!/usr/bin/env python3
"""Real function-calling agent loop for Leverage AI.

Replaces the [[TAG: value]] text-parsing approach (see tools.py's
extract_tool_call) with actual structured tool calling against Groq's
OpenAI-compatible API. This eliminates an entire class of bugs the
text-tag approach had: placeholder echoing, multiple tags in one reply,
ambiguous tag-priority ordering - none of those are possible when the
model is choosing from a fixed schema instead of free-generating syntax.

Uses llama-3.3-70b-versatile by default (see providers.groq_tools) since
tool-use instruction-following is meaningfully better at 70B than the
8B-instant model used elsewhere in this codebase for plain chat/quick/
write/etc - those pipelines don't need this and are left untouched.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from leverage_ai.providers import groq_tools
from leverage_ai.tools import TOOL_SCHEMA, get_file_content, list_dir, run_bash
from leverage_ai.exceptions import ProviderError, ProviderAuthError, ProviderConnectionError

logger = logging.getLogger("leverage_ai.agent")

SYSTEM_PROMPT = (
    "You are a helpful, concise assistant with real access to the user's local "
    "filesystem and shell through the read_file, list_dir, and run_bash tools. "
    "Use them whenever the user asks about local files, directories, or commands - "
    "don't guess or describe what you expect to find before calling a tool. After a "
    "tool result comes back, answer using its SPECIFIC contents (real file/directory "
    "names, real command output) rather than a vague summary. Don't call a tool again "
    "if you already have the information you need from a previous result in this "
    "conversation. Keep replies to one short paragraph unless detail is requested."
)


def confirm_mutating_command_default(cmd: str) -> bool:
    """Default confirmation gate for mutating bash commands - same UX as
    the old tag-based loop in __main__.py. Callers can override.
    """
    print(f"\n  [bash] Model wants to run a MUTATING command:")
    print(f"    {cmd}")
    answer = input("  Allow? [y/N] ").strip().lower()
    return answer == "y"


def _execute_tool_call(name: str, arguments: Dict[str, Any], confirm_fn) -> str:
    """Dispatch a single structured tool call to its real implementation."""
    if name == "read_file":
        path = arguments.get("path", "")
        print(f"  [tool] reading file: {path}")
        return get_file_content(path)
    elif name == "list_dir":
        path = arguments.get("path", "~")
        print(f"  [tool] listing dir: {path}")
        return list_dir(path)
    elif name == "run_bash":
        command = arguments.get("command", "")
        print(f"  [tool] bash: {command}")
        executed, result = run_bash(command, confirm_fn=confirm_fn)
        if not executed:
            print(f"  [tool] {result}")
        return result
    else:
        return f"Error: unknown tool '{name}'"


def run_agent_turn(user_message: str, history: Optional[List[Dict[str, Any]]] = None,
                   model: str = "llama-3.3-70b-versatile", max_hops: int = 6,
                   confirm_fn=None) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Run one full user turn through the real tool-calling agent loop.

    history: prior turns as OpenAI-style messages (role: user/assistant/
    tool), NOT the old convo format used by the tag-based pipelines.

    Returns (final_answer_or_None, new_messages_to_persist). new_messages
    starts at the user message and includes every tool-call/tool-result
    exchange plus the final assistant answer - the caller should append
    all of it to history (this IS how OpenAI-style tool calling expects
    history to look; unlike the old text-tag system, intermediate tool
    messages here are structured data, not free text the model could
    misinterpret as past narration).
    """
    if confirm_fn is None:
        confirm_fn = confirm_mutating_command_default

    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    user_turn = {"role": "user", "content": user_message}
    messages.append(user_turn)
    new_messages: List[Dict[str, Any]] = [user_turn]

    hops = 0
    while hops < max_hops:
        hops += 1
        try:
            response = groq_tools(messages, TOOL_SCHEMA, model=model)
        except (ProviderAuthError, ProviderConnectionError, ProviderError) as e:
            logger.warning(f"groq_tools failed: {e}")
            print(f"  [agent] provider error: {e}")
            return None, new_messages

        if response.status_code != 200:
            print(f"  [agent] HTTP {response.status_code} from Groq")
            try:
                print(f"  [agent] {response.json()}")
            except Exception:
                pass
            return None, new_messages

        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls")

        if not tool_calls:
            # Final answer - no more tools requested
            content = message.get("content", "") or ""
            new_messages.append({"role": "assistant", "content": content})
            return content, new_messages

        # Record the assistant's tool-call request, then execute each
        # call and append its result, per OpenAI's tool-calling protocol.
        messages.append(message)
        new_messages.append(message)
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                arguments = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {}

            result = _execute_tool_call(name, arguments, confirm_fn)
            tool_msg = {
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": result,
            }
            messages.append(tool_msg)
            new_messages.append(tool_msg)

    print(f"  [agent] reached max hops ({max_hops}) without a final answer")
    return None, new_messages
