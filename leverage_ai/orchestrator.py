#!/usr/bin/env python3
"""Core orchestration logic for Leverage AI - chains, routing, classification."""

import sys
import time
import logging
import random
import math
from typing import List, Tuple, Optional, Dict, Any

from leverage_ai.config import (
    ALL_PROVIDERS, CHAIN_SPEC, CHAIN_ARCH, CHAIN_BUILD, CHAIN_REVIEW,
    CHAIN_DRAFT, CHAIN_FINAL, CHAIN_ANALYZE, CHAIN_QUICK, CHAIN_CHAT
)
from leverage_ai.providers import PROVIDERS
from leverage_ai.cache import load_cache, save_cache
from leverage_ai.semantic_cache import semantic_cache_lookup, semantic_cache_store
from leverage_ai.code_utils import compress_prompt
from leverage_ai.exceptions import (
    ProviderError, ProviderTimeout, ProviderAuthError, ProviderRateLimit,
    ProviderResponseError, ProviderNotAvailable, ProviderConnectionError
)
from leverage_ai.colors import (
    provider, chain, error as err_color, warning as warn_color,
    success, info, token_count
)
from leverage_ai.state import (
    record_latency, get_provider_latency_stats, record_provider_failure,
    can_retry_provider, reset_provider_backoff
)

logger = logging.getLogger("leverage_ai.orchestrator")

usage_log: List[Tuple[str, str, Dict[str, Any]]] = []
FAILED_THIS_SESSION = set()

# ── Chain Management ──

def heal_chain(chain: List[str], depleted: List[str]) -> List[str]:
    """Rebuild chain by adding available providers not in original chain."""
    alive = [p for p in ALL_PROVIDERS if p not in depleted]
    healed = [p for p in chain if p not in depleted]
    for p in alive:
        if p not in healed:
            healed.append(p)
    return healed if healed else chain


def exponential_backoff_with_jitter(attempt: int, max_backoff: float = 30.0) -> float:
    """Calculate exponential backoff with jitter.
    
    Returns: seconds to wait before retry
    Formula: min(max_backoff, base * (2 ^ attempt) + random_jitter)
    """
    base = 1.0
    exponential = base * math.pow(2, attempt)
    jitter = random.uniform(0, exponential * 0.1)  # +0-10% jitter
    return min(max_backoff, exponential + jitter)


def parse_retry_after(response) -> Optional[int]:
    """Parse Retry-After header from response.
    
    Returns: seconds to wait, or None if not present
    """
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    
    try:
        # Try parsing as seconds first
        return int(retry_after)
    except ValueError:
        # Could be HTTP-date format, just use default
        logger.debug(f"Could not parse Retry-After: {retry_after}")
        return None


def score_provider_for_routing(provider_name: str, state: Dict[str, Any]) -> float:
    """Score provider for selection based on latency and reliability.
    
    Higher score = better choice.
    Factors:
    - Latency (prefer faster providers)
    - Reliability (prefer lower strike count)
    - Token usage (slight preference for less-used)
    """
    latency_stats = get_provider_latency_stats(state, provider_name)
    p95_latency = latency_stats.get("p95", 1000)  # Default 1s if no data
    
    backoff = state.get("provider_backoff", {}).get(provider_name, {})
    strikes = backoff.get("strikes", 0)
    
    usage_tokens = state.get("tokens", {}).get(provider_name, 0)
    
    # Score: lower is better
    # p95_latency (higher latency = worse)
    # strikes (more failures = worse, exponentially)
    # normalized usage (prefer less used)
    
    latency_score = 1.0 / (1.0 + (p95_latency / 1000.0))  # 0-1, higher is better
    reliability_score = 1.0 / (1.0 + strikes * strikes)  # 0-1, higher is better
    usage_score = 1.0 / (1.0 + (usage_tokens / 100000.0))  # 0-1, higher is better
    
    # Weighted score
    return (latency_score * 0.5) + (reliability_score * 0.35) + (usage_score * 0.15)


def try_chain(chain: List[str], prompt: str, max_tokens: int, 
              state: Dict[str, Any], model_override: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], Optional[str]]:
    """Try providers in chain order with intelligent error handling.
    
    Returns: (provider_name, content) or (None, None) if all fail
    """
    if not chain:
        logger.error("Empty chain provided")
        return None, None
    
    skipped = []
    
    # Smart provider selection: score by latency + reliability + usage
    scored_chain = [(p, score_provider_for_routing(p, state)) for p in chain]
    scored_chain.sort(key=lambda x: -x[1])  # Sort by score descending
    sorted_chain = [p for p, _ in scored_chain]
    
    # Apply minute-based rotation for additional load balancing
    now = time.localtime()
    minute_offset = (now.tm_hour * 60 + now.tm_min) % max(1, len(sorted_chain))
    rotated = sorted_chain[minute_offset:] + sorted_chain[:minute_offset]
    
    for prov in rotated:
        # Check if provider is marked as depleted
        if prov in FAILED_THIS_SESSION:
            logger.debug(f"Skipping {prov}: blacklisted this session")
            continue
        if prov in state.get("depleted", []):
            skipped.append(prov)
            logger.debug(f"Skipping {prov}: marked as permanently depleted")
            continue
        
        # Check if provider is in backoff period
        if not can_retry_provider(state, prov):
            backoff_state = state.get("provider_backoff", {}).get(prov, {})
            retry_after = backoff_state.get("retry_after", 0)
            wait_time = retry_after - int(time.time())
            logger.debug(f"Skipping {prov}: in backoff for {wait_time}s")
            continue
        
        # Get provider function and parser
        if prov not in PROVIDERS:
            logger.warning(f"Provider {prov} not in registry")
            continue
        
        fn, parser = PROVIDERS[prov]
        
        try:
            # Build kwargs for provider
            kwargs = {"prompt": prompt, "max_tokens": max_tokens}
            if model_override and prov in model_override:
                kwargs["model"] = model_override[prov]
            
            # Call provider with timing
            logger.debug(f"Calling {prov}...")
            call_start = time.time()
            response = fn(**kwargs)
            latency_ms = (time.time() - call_start) * 1000
            
            # Record latency
            record_latency(state, prov, latency_ms)
            
        except ProviderAuthError as e:
            logger.warning(f"{prov}: Auth error - {e}")
            state.setdefault("depleted", []).append(prov)
            from leverage_ai.state import save_state
            save_state(state)
            print(f"  {provider(prov)} {warn_color('Auth failed')} - marking as permanently depleted")
            record_provider_failure(state, prov, "auth_error")
            continue
            
        except ProviderRateLimit as e:
            logger.warning(f"{prov}: Rate limited")
            # Don't mark as permanently depleted, use backoff
            record_provider_failure(state, prov, "rate_limit", retry_after=60)
            from leverage_ai.state import save_state
            save_state(state)
            print(f"  {provider(prov)} {warn_color('Rate limited')} - backing off 60s")
            continue
            
        except ProviderTimeout:
            logger.warning(f"{prov}: Timeout")
            record_provider_failure(state, prov, "timeout", retry_after=30)
            print(f"  {provider(prov)} {warn_color('Timeout')}, trying next...")
            continue
            
        except ProviderConnectionError as e:
            logger.warning(f"{prov}: Connection error - {e}")
            FAILED_THIS_SESSION.add(prov)
            record_provider_failure(state, prov, "connection_error", retry_after=120)
            print(f"  {provider(prov)} {warn_color('Connection error - Blacklisted for session')}")
            continue
            
        except ProviderError as e:
            logger.warning(f"{prov}: Provider error - {e}")
            record_provider_failure(state, prov, "provider_error", retry_after=45)
            print(f"  {provider(prov)} {err_color('Error')}: {e}")
            continue
        
        # Check HTTP status code
        status_code = response.status_code
        
        if status_code == 401 or status_code == 403:
            logger.warning(f"{prov}: HTTP {status_code} - auth/permission error")
            state.setdefault("depleted", []).append(prov)
            from leverage_ai.state import save_state
            save_state(state)
            print(f"  {provider(prov)} {err_color(f'HTTP {status_code}')} - auth/permission error")
            record_provider_failure(state, prov, "http_auth_error")
            continue
        
        if status_code == 429 or status_code == 402:
            logger.warning(f"{prov}: HTTP {status_code} - rate limited or quota exceeded")
            # Parse Retry-After header
            retry_after = parse_retry_after(response)
            if retry_after is None:
                retry_after = 60  # Default to 60s if not specified
            record_provider_failure(state, prov, "http_rate_limit", retry_after=retry_after)
            from leverage_ai.state import save_state
            save_state(state)
            print(f"  {provider(prov)} {err_color(f'HTTP {status_code}')} - backing off {retry_after}s")
            continue
        
        if status_code >= 500:
            logger.warning(f"{prov}: HTTP {status_code} - server error")
            # Transient error, backoff but don't mark as permanently depleted
            record_provider_failure(state, prov, "http_server_error", retry_after=30)
            print(f"  {provider(prov)} {warn_color(f'Server error {status_code}')}, trying next...")
            continue
        
        if status_code != 200:
            logger.warning(f"{prov}: Unexpected HTTP {status_code}")
            print(f"  {provider(prov)} {warn_color(f'HTTP {status_code}')}, trying next...")
            continue
        
        # Parse response
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"{prov}: Failed to parse JSON - {e}")
            print(f"  {provider(prov)} {err_color('Invalid JSON')}, trying next...")
            continue
        
        # Call parser
        try:
            usage, content = parser(data)
        except ProviderResponseError as e:
            logger.error(f"{prov}: Response parsing failed - {e}")
            print(f"  {provider(prov)} {err_color('Parse failed')}, trying next...")
            continue
        except Exception as e:
            logger.error(f"{prov}: Unexpected error during parsing - {e}")
            print(f"  {provider(prov)} {err_color('Unexpected error')}, trying next...")
            continue
        
        # Check for empty response
        if not content or not content.strip():
            logger.warning(f"{prov}: Empty response")
            print(f"  {provider(prov)} {warn_color('Empty response')}, trying next...")
            continue
        
        # Success! Reset backoff state
        reset_provider_backoff(state, prov)
        
        logger.info(f"{prov}: Success ({usage.get('prompt_tokens', 0)} -> {usage.get('completion_tokens', 0)} tokens)")
        model_name = data.get("model", kwargs.get("model", prov))
        usage_log.append((prov, model_name, usage))
        print(f"  {success(chr(10003))} {provider(prov)} {token_count(str(usage.get('prompt_tokens', 0)) + '->' + str(usage.get('completion_tokens', 0)))} {info(f'({latency_ms:.0f}ms)')}")
        return prov, content
    
    # All providers failed
    if skipped:
        print(f"  {err_color('ERROR')} All providers failed. Skipped {len(skipped)}: {', '.join(skipped)}")
    else:
        print(f"  {err_color('ERROR')} No providers available in chain")
    
    return None, None


# ── Request Classification ──

def classify(idea: str) -> str:
    """Classify user request into pipeline type."""
    kw = idea.lower()
    words = set(kw.split())

    # File / command requests - route to chat, where tool-calling is wired up
    tool_triggers = ["read the", "read my", "open the", "open my", "show me the contents",
                      "list the", "list my", "ls ", "run the command", "run this command",
                      "see my local files", "see my files", "check the file", "what's in the file",
                      "what's in this file", "cat "]
    if any(trigger in kw for trigger in tool_triggers):
        return "chat"

    # Memory commands
    memory_words = {"remember", "forget", "show memory", "clear memory"}
    if any(word in kw for word in memory_words):
        return "memory"
    
    # Usage check
    if "usage" in kw or "quota" in kw or "limit" in kw:
        return "usage"
    
    # Analysis requests
    analyze_words = {"explain", "compare", "contrast", "why", "analyze", "analysis", 
                     "difference", "pros and cons", "what's"}
    if words & analyze_words:
        return "analyze"
    
    # Code requests
    code_triggers = ["write a program", "write code", "build a", "create a script", 
                     "fix this code", "debug", "implement", "function to", "app that", 
                     "script to", "code to", "write python", "write javascript"]
    if any(trigger in kw for trigger in code_triggers):
        return "code"
    
    # Writing requests
    write_words = {"poem", "story", "haiku", "email", "essay", "letter", 
                   "article", "write me", "draft a", "compose"}
    if words & write_words:
        return "write"
    
    # Quick factual questions
    quick_triggers = ["what is", "what's", "who is", "when", "where", "how many", 
                      "define", "capital of", "tell me about"]
    if any(trigger in kw for trigger in quick_triggers):
        return "quick"
    
    # Default: conversational chat
    return "chat"


# ── Pipeline Stages ──

def run_stage(provider_chain: List[str], prompt: str, max_tokens: int, state: Dict[str, Any],
              label: str = "", use_cache: bool = True, convo: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
    """Execute a single pipeline stage with intelligent chain management.
    
    Args:
        provider_chain: List of provider names in order of preference
        prompt: The prompt to send to providers
        max_tokens: Maximum tokens to request
        state: User state dict
        label: Label for logging
        use_cache: Whether to check cache first (exact then semantic)
        convo: Conversation history to update
    
    Returns:
        Content from first successful provider, or None
    """
    
    # Check exact-match cache first
    if use_cache:
        cached = load_cache(prompt, max_tokens)
        if cached:
            logger.info(f"Exact cache hit for: {label}")
            print(f"  {success('⚡')} {info('cache hit (exact)')}")
            print(cached)
            usage_log.append(("Cache", "", {"prompt_tokens": 0, "completion_tokens": len(cached.split())}))
            return cached
    
    # Check semantic cache
    if use_cache:
        semantic_hit = semantic_cache_lookup(prompt, max_tokens)
        if semantic_hit:
            logger.info(f"Semantic cache hit for: {label}")
            print(f"  {success('⚡')} {info('cache hit (semantic)')}")
            print(semantic_hit)
            usage_log.append(("Cache", "", {"prompt_tokens": 0, "completion_tokens": len(semantic_hit.split())}))
            return semantic_hit
    
    # Compress prompt if too long
    original_len = len(prompt.split())
    if original_len > max_tokens * 0.7:
        prompt = compress_prompt(prompt, max_tokens)
        compressed_len = len(prompt.split())
        if compressed_len < original_len:
            logger.info(f"Compressed prompt: {original_len} -> {compressed_len}")
            print(f"  {info('compressed')} {original_len} → {compressed_len} words")
    
    # Heal depleted providers
    depleted = state.get("depleted", [])
    active_chain = [p for p in provider_chain if p not in depleted]
    
    if not active_chain:
        print(f"  {err_color('ERROR')} All providers in chain are permanently depleted!")
        return None
    
    if len(active_chain) < len(provider_chain):
        skipped = [p for p in provider_chain if p in depleted]
        chain_str = chain(' → '.join(active_chain[:3]))
        print(f"  {chain_str} {warn_color(f'(skipped: {len(skipped)})')}")
    else:
        print(f"  {chain(' → '.join(active_chain[:3]))}")
    
    # Try chain
    prov, content = try_chain(active_chain, prompt, max_tokens, state)
    
    if content:
        # Save to exact-match cache
        save_cache(prompt, max_tokens, content)
        
        # Save to semantic cache
        semantic_cache_store(prompt, max_tokens, content)
        
        # Print label and content
        if label:
            from leverage_ai.colors import section
            print(f"\n{section('─' * 40)}")
            print(f"{section(label)}")
            print(f"{section('─' * 40)}")
        print(content)
        
        # Add to conversation history
        if convo is not None:
            convo.append({"role": "assistant", "content": content})
        
        return content
    
    print(f"  {err_color('ERROR')} No providers available for '{label}'")
    return None


def last_header(label: str = "") -> None:
    """Print summary of last API call."""
    if not usage_log:
        return
    
    prov, model, usage = usage_log[-1]
    
    if not isinstance(usage, dict):
        return
    
    pt = usage.get("prompt_tokens", 0) or 0
    ct = usage.get("completion_tokens", 0) or 0
    total = pt + ct
    
    short_model = model.split("/")[-1][:20] if model else prov
    
    print(f"[{prov} {short_model}] {pt}->{ct}={total} tokens  {label}")
