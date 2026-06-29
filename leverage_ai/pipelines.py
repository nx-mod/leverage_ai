#!/usr/bin/env python3
"""Pipeline implementations for different request types."""

import logging
from typing import Optional, List, Dict, Any

from leverage_ai.config import (
    CHAIN_SPEC, CHAIN_ARCH, CHAIN_BUILD, CHAIN_REVIEW,
    CHAIN_DRAFT, CHAIN_FINAL, CHAIN_ANALYZE, CHAIN_QUICK, CHAIN_CHAT
)
from leverage_ai.orchestrator import run_stage, usage_log
from leverage_ai.cache import load_cache
from leverage_ai.code_utils import extract_code, save_code, try_run, install_deps, show_files
from leverage_ai.memory import get_relevant_context, get_conversation_context

logger = logging.getLogger("leverage_ai.pipelines")


def pipeline_quick(idea: str, state: Dict[str, Any], convo: Optional[List[Dict[str, str]]] = None):
    """Handle simple factual questions with fast, cheap provider."""
    logger.debug("Quick pipeline")
    
    convo_context = get_conversation_context(convo) if convo else ""
    
    prompt = ("You have no filesystem/tool access in this mode - if asked about local files "
              "or running commands, say so rather than guessing. "
              "Answer concisely and directly. No preamble. 2-3 sentences max.")
    if convo_context:
        prompt += f"\n\nRecent conversation:\n{convo_context}"
    prompt += f"\n\nQuestion: {idea}"
    
    run_stage(CHAIN_QUICK, prompt, 200, state, "Quick Answer", use_cache=True, convo=convo)


TOOL_INSTRUCTIONS = """You have NO ability to see, read, or access the local filesystem, \
run commands, or remember anything beyond what's shown to you in this prompt. You are a \
text-completion API call with no persistent state and no tools unless explicitly given below.

You DO have access to 3 tools. To use one, end your reply with a tag containing a REAL, \
SPECIFIC value - never copy the example text literally, always substitute the actual path \
or command the user is asking about.

Tool 1 - read a file. Example: if the user asks to read their readme, end with:
[[READ_FILE: ~/leverage_ai/README.md]]

Tool 2 - list a directory. Example: if the user asks what's in their home folder, end with:
[[LIST_DIR: ~]]

Tool 3 - run a shell command. Example: if the user asks to check git status, end with:
[[BASH: git status]]

Rules:
- Only ONE tag per reply, only when the user is actually asking to read/list/run something.
- The text after the colon must be a real path or real command, never the literal words \
"path", "shell command", "filename", or similar placeholders - those will fail.
- If you don't know the exact path, guess a reasonable real one (e.g. ~/README.md, ~, \
~/project_name) rather than typing a placeholder word.
- Never claim you already read, opened, or saw something unless a tool result for it \
appears above in this conversation. If a tool call just failed, tell the user plainly what \
failed and try a corrected real value - don't pretend it worked or that you "remember" \
unrelated past attempts."""


def pipeline_chat(idea: str, state: Dict[str, Any], convo: Optional[List[Dict[str, str]]] = None,
                   tool_result: Optional[str] = None):
    """LEGACY / UNUSED in the main flow as of the agent.py rewrite.

    This text-tag approach ([[READ_FILE: ...]] etc, parsed by
    tools.extract_tool_call) had several hard-to-fully-fix failure modes
    on small/fast models: placeholder echoing, multiple tags in one
    reply with ambiguous priority, and pre-tool-call confabulation. It's
    superseded by leverage_ai.agent.run_agent_turn, which uses Groq's
    real structured function-calling API instead of free-text tags.

    Left in place (not deleted) as a manual fallback in case the
    function-calling API path is ever unavailable - not currently
    wired into __main__.py's dispatch loop.
    """
    logger.debug("Chat pipeline")
    
    convo_context = get_conversation_context(convo) if convo else ""
    
    prompt = TOOL_INSTRUCTIONS + "\n\nBe friendly, helpful, and concise. One paragraph max."
    if convo_context:
        prompt += f"\n\nRecent conversation:\n{convo_context}"
    if tool_result:
        prompt += (f"\n\nTool result (this is REAL data, already retrieved):\n{tool_result}\n\n"
                   f"Answer the user's question using the SPECIFIC contents above - name actual "
                   f"file/directory names or actual command output, don't describe it vaguely "
                   f"(e.g. say \"I see config.py, README.md, and .git\" not \"some configuration "
                   f"files\"). Do not emit another tool tag unless you genuinely need a DIFFERENT "
                   f"piece of information than what's already shown above.")
    prompt += f"\n\nMessage: {idea}"
    
    return run_stage(CHAIN_CHAT, prompt, 400, state, "Response", use_cache=(tool_result is None), convo=None)


def pipeline_code(idea: str, state: Dict[str, Any], noexec: bool = False, 
                  mem: Optional[Dict[str, Any]] = None):
    """Handle code generation requests with full pipeline."""
    logger.debug("Code pipeline")
    
    context = get_relevant_context(mem, idea) if mem else []
    context_str = "\n\nRelevant context from previous conversations:\n" + "\n".join(context) if context else ""
    
    word_count = len(idea.split())
    
    # Check if simple code request was cached
    if word_count < 50:
        cached_impl = load_cache(f"code:{idea}", 2500)
        if cached_impl:
            print("  [cache hit] Code implementation")
            blocks = extract_code(cached_impl)
            if blocks:
                paths = save_code(blocks, idea)
                for p in paths:
                    print(f"  [saved] {p}")
                install_deps(paths)
                show_files(paths)
                try_run(paths, idea, noexec)
                usage_log.append(("Cache", "", {"prompt_tokens": 0, "completion_tokens": len(cached_impl.split())}))
            return
    
    if word_count < 30:
        # Simple request - single stage
        impl = run_stage(
            CHAIN_BUILD,
            f"Write clean, working code for:\n{idea}{context_str}",
            2000, state, "Implementation", use_cache=False
        )
        if impl:
            blocks = extract_code(impl)
            if blocks:
                paths = save_code(blocks, idea)
                for p in paths:
                    print(f"  [saved] {p}")
                install_deps(paths)
                show_files(paths)
                try_run(paths, idea, noexec)
    else:
        # Complex request - full pipeline
        spec = run_stage(
            CHAIN_SPEC,
            f"Analyze this code request. What are core requirements, edge cases, and design decisions? Be thorough but concise:\n{idea}{context_str}",
            400, state, "Analysis", use_cache=False
        )
        if not spec:
            return
        
        arch = run_stage(
            CHAIN_ARCH,
            f"Design the implementation approach:\n\nRequest: {idea}\n\nAnalysis: {spec}{context_str}",
            500, state, "Architecture", use_cache=False
        )
        if not arch:
            return
        
        impl = run_stage(
            CHAIN_BUILD,
            f"Implement this solution:\n\nRequest: {idea}\n\nAnalysis: {spec}\n\nArchitecture: {arch}{context_str}",
            2500, state, "Implementation", use_cache=False
        )
        if impl:
            blocks = extract_code(impl)
            if blocks:
                paths = save_code(blocks, idea)
                for p in paths:
                    print(f"  [saved] {p}")
                install_deps(paths)
                show_files(paths)
                try_run(paths, idea, noexec)
            
            # Get a code review
            run_stage(
                CHAIN_REVIEW,
                f"Review this code critically. Identify bugs, security issues, performance problems:\n{impl}",
                800, state, "Review", use_cache=False
            )


def pipeline_write(idea: str, state: Dict[str, Any], mem: Optional[Dict[str, Any]] = None):
    """Handle creative writing requests with draft -> polish pipeline."""
    logger.debug("Write pipeline")
    
    context = get_relevant_context(mem, idea) if mem else []
    context_str = "\n\nRelevant context:\n" + "\n".join(context) if context else ""
    
    # Draft stage
    draft = run_stage(
        CHAIN_DRAFT,
        f"Write a first draft:\n{idea}{context_str}",
        500, state, "Draft", use_cache=False
    )
    if not draft:
        return
    
    # Polish stage
    run_stage(
        CHAIN_FINAL,
        f"Polish and complete this draft:\n\nRequest: {idea}\n\nDraft: {draft}{context_str}",
        1500, state, "Final", use_cache=False
    )


def pipeline_analyze(idea: str, state: Dict[str, Any], mem: Optional[Dict[str, Any]] = None):
    """Handle analysis requests with deep reasoning."""
    logger.debug("Analyze pipeline")
    
    context = get_relevant_context(mem, idea) if mem else []
    context_str = "\n\nRelevant context:\n" + "\n".join(context) if context else ""
    
    # Initial analysis
    analysis = run_stage(
        CHAIN_ANALYZE,
        f"Analyze:\n{idea}{context_str}",
        1000, state, "Analysis", use_cache=False
    )
    if not analysis:
        return
    
    # Deeper analysis
    run_stage(
        CHAIN_ANALYZE,
        f"Provide a deeper, more comprehensive analysis:\n\nOriginal request: {idea}\n\nInitial analysis: {analysis}{context_str}",
        1000, state, "Deeper Analysis", use_cache=False
    )
