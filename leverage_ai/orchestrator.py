#!/usr/bin/env python3
"""Core orchestration logic for Leverage AI - chains, routing, classification."""

import sys
import time
import logging
from typing import List, Tuple, Optional, Dict, Any

from leverage_ai.config import (
    ALL_PROVIDERS, CHAIN_SPEC, CHAIN_ARCH, CHAIN_BUILD, CHAIN_REVIEW,
    CHAIN_DRAFT, CHAIN_FINAL, CHAIN_ANALYZE, CHAIN_QUICK, CHAIN_CHAT
)
from leverage_ai.providers import PROVIDERS
from leverage_ai.cache import load_cache, save_cache
from leverage_ai.code_utils import compress_prompt
from leverage_ai.exceptions import (
    ProviderError, ProviderTimeout, ProviderAuthError, ProviderRateLimit,
    ProviderResponseError, ProviderNotAvailable, ProviderConnectionError
)
from leverage_ai.colors import (
    provider, chain, error as err_color, warning as warn_color,
    success, info, token_count
)

logger = logging.getLogger("leverage_ai.orchestrator")

usage_log: List[Tuple[str, str, Dict[str, Any]]] = []

# ── Chain Management ──

def heal_chain(chain: List[str], depleted: List[str]) -> List[str]:
    """Rebuild chain by adding available providers not in original chain."""
    alive = [p for p in ALL_PROVIDERS if p not in depleted]
    healed = [p for p in chain if p not in depleted]
    for p in alive:
        if p not in healed:
            healed.append(p)
    return healed if healed else chain


def try_chain(chain: List[str], prompt: str, max_tokens: int, 
              state: Dict[str, Any], model_override: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], Optional[str]]:
    """Try providers in chain order with intelligent error handling.
    
    Returns: (provider_name, content) or (None, None) if all fail
    """
    if not chain:
        logger.error("Empty chain provided")
        return None, None
    
    skipped = []
    
    # Smart provider selection: prioritize least-used providers
    usage_by_provider = {}
    for key, count in state.get("tokens", {}).items():
        prov = key.split("/")[0] if "/" in key else key
        usage_by_provider[prov] = usage_by_provider.get(prov, 0) + count
    
    sorted_chain = sorted(chain, key=lambda p: usage_by_provider.get(p, 0))
    
    # Apply minute-based rotation for load balancing
    now = time.localtime()
    minute_offset = (now.tm_hour * 60 + now.tm_min) % len(sorted_chain) if len(sorted_chain) > 2 else 0
    rotated = sorted_chain[minute_offset:] + sorted_chain[:minute_offset] if len(sorted_chain) > 2 else sorted_chain
    
    for prov in rotated:
        # Check if provider is marked as depleted
        if prov in state.get("depleted", []):
            skipped.append(prov)
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
            
            # Call provider
            logger.debug(f"Calling {prov}...")
            response = fn(**kwargs)
            
        except ProviderAuthError as e:
            logger.warning(f"{prov}: Auth error - {e}")
            state.setdefault("depleted", []).append(prov)
            from leverage_ai.state import save_state
            save_state(state)
            print(f"  {provider(prov)} {warn_color('Auth failed')} - marking as depleted")
            continue
            
        except ProviderRateLimit as e:
            logger.warning(f"{prov}: Rate limited")
            state.setdefault("depleted", []).append(prov)
            from leverage_ai.state import save_state
            save_state(state)
            print(f"  {provider(prov)} {warn_color('Rate limited')} - marking as depleted")
            continue
            
        except ProviderTimeout:
            logger.warning(f"{prov}: Timeout")
            print(f"  {provider(prov)} {warn_color('Timeout')}, trying next...")
            continue
            
        except ProviderConnectionError as e:
            logger.warning(f"{prov}: Connection error - {e}")
            print(f"  {provider(prov)} {warn_color('Connection error')}, trying next...")
            continue
            
        except ProviderError as e:
            logger.warning(f"{prov}: Provider error - {e}")
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
            continue
        
        if status_code == 429 or status_code == 402:
            logger.warning(f"{prov}: HTTP {status_code} - rate limited or quota exceeded")
            state.setdefault("depleted", []).append(prov)
            from leverage_ai.state import save_state
            save_state(state)
            print(f"  {provider(prov)} {err_color(f'HTTP {status_code}')} - quota exceeded")
            continue
        
        if status_code >= 500:
            logger.warning(f"{prov}: HTTP {status_code} - server error")
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
        
        # Success!
        logger.info(f"{prov}: Success ({usage.get('prompt_tokens', 0)} -> {usage.get('completion_tokens', 0)} tokens)")
        model_name = data.get("model", kwargs.get("model", prov))
        usage_log.append((prov, model_name, usage))
        print(f"  {success('✓')} {provider(prov)} {token_count(f'{usage.get(\"prompt_tokens\", 0)}->{usage.get(\"completion_tokens\", 0)}')}")
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

def run_stage(chain: List[str], prompt: str, max_tokens: int, state: Dict[str, Any],
              label: str = "", use_cache: bool = True, convo: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
    """Execute a single pipeline stage with intelligent chain management.
    
    Args:
        chain: List of provider names in order of preference
        prompt: The prompt to send to providers
        max_tokens: Maximum tokens to request
        state: User state dict
        label: Label for logging
        use_cache: Whether to check cache first
        convo: Conversation history to update
    
    Returns:
        Content from first successful provider, or None
    """
    
    # Check cache
    if use_cache:
        cached = load_cache(prompt, max_tokens)
        if cached:
            logger.info(f"Cache hit for: {label}")
            print(f"  {success('⚡')} {info('cache hit')}")
            print(cached)
            usage_log.append(("Cache", "", {"prompt_tokens": 0, "completion_tokens": len(cached.split())}))
            return cached
    
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
    active_chain = [p for p in chain if p not in depleted]
    
    if not active_chain:
        print(f"  {err_color('ERROR')} All providers in chain are depleted!")
        return None
    
    if len(active_chain) < len(chain):
        skipped = [p for p in chain if p in depleted]
        chain_str = chain(' → '.join(active_chain[:3]))
        print(f"  {chain_str} {warn_color(f'(skipped: {len(skipped)})')}")
    else:
        print(f"  {chain(' → '.join(active_chain[:3]))}")
    
    # Try chain
    prov, content = try_chain(active_chain, prompt, max_tokens, state)
    
    if content:
        # Save to cache
        save_cache(prompt, max_tokens, content)
        
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
