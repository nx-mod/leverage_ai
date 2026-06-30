#!/usr/bin/env python3
"""API provider wrappers with proper error handling and response validation."""

import os
import requests
import json
import logging
from typing import Tuple, Dict, Any, Optional

from leverage_ai.config import TIMEOUT, LONG_TIMEOUT
from leverage_ai.exceptions import (
    ProviderError, ProviderTimeout, ProviderConnectionError,
    ProviderAuthError, ProviderRateLimit, ProviderResponseError
)

logger = logging.getLogger("leverage_ai.providers")

# Keys are read live via os.getenv() at call time (not snapshotted at
# import time) so that runtime overrides set through the /providers
# panel (provider_settings.set_key) take effect immediately without
# restarting the process.

def _key(env_var: str) -> Optional[str]:
    return os.getenv(env_var)

# ── HTTP Wrapper ──

def call(method: str, url: str, headers: Dict[str, str], 
         json_data: Dict[str, Any], timeout: Tuple[int, int] = TIMEOUT) -> requests.Response:
    """Make HTTP request with proper error handling."""
    try:
        logger.debug(f"{method} {url}")
        r = requests.request(method, url, headers=headers, json=json_data, timeout=timeout)
        return r
    except requests.Timeout as e:
        raise ProviderTimeout(f"Request timed out after {timeout}s")
    except requests.ConnectionError as e:
        raise ProviderConnectionError(f"Connection failed: {str(e)}")
    except Exception as e:
        raise ProviderError(f"HTTP request failed: {str(e)}")

# ── Provider Functions ──

def groq(prompt: str, model: str = "llama-3.1-8b-instant", max_tokens: int = 500) -> requests.Response:
    """Groq API."""
    groq_key = _key("GROQ_API_KEY")
    if not groq_key:
        raise ProviderAuthError("Groq: No API key configured (GROQ_API_KEY)")
    
    return call("POST", "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
        {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
        timeout=TIMEOUT)


def groq_tools(messages: list, tools: list, model: str = "llama-3.3-70b-versatile",
               max_tokens: int = 800, tool_choice: str = "auto") -> requests.Response:
    """Groq API with real OpenAI-compatible function calling.

    Unlike groq() above, this takes a full messages list (so multi-turn
    tool-call/tool-result history can be sent properly) and a tools
    schema. The model either returns a normal text reply or a
    message.tool_calls list with structured {name, arguments} - no text
    tag parsing, no placeholder-echoing failure mode, because the model
    isn't free-generating the call syntax.

    Defaults to llama-3.3-70b-versatile rather than the 8b-instant model
    used elsewhere: tool-use instruction-following is meaningfully worse
    on the smaller model, and 70b is still free-tier on Groq.
    """
    groq_key = _key("GROQ_API_KEY")
    if not groq_key:
        raise ProviderAuthError("Groq: No API key configured (GROQ_API_KEY)")

    return call("POST", "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
        {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "max_tokens": max_tokens,
        },
        timeout=LONG_TIMEOUT)

def cloudflare(prompt: str, model: str = "@cf/meta/llama-3.2-3b-instruct", max_tokens: int = 500) -> requests.Response:
    """Cloudflare Workers AI."""
    cf_key = _key("CLOUDFLARE_API_KEY")
    cf_acct = _key("CF_ACCOUNT_ID")
    if not cf_key:
        raise ProviderAuthError("Cloudflare: No API key configured (CLOUDFLARE_API_KEY)")
    if not cf_acct:
        raise ProviderAuthError("Cloudflare: No account ID configured (CF_ACCOUNT_ID)")
    
    return call("POST", f"https://api.cloudflare.com/client/v4/accounts/{cf_acct}/ai/run/{model}",
        {"Authorization": f"Bearer {cf_key}"},
        {"prompt": prompt, "max_tokens": max_tokens},
        timeout=TIMEOUT)

def hyper(prompt: str, model: str = "llama-3.3-70b-instruct", max_tokens: int = 2500) -> requests.Response:
    """Charm Hyper API."""
    hyper_key = _key("HYPER_API_KEY")
    if not hyper_key:
        raise ProviderAuthError("Charm Hyper: No API key configured (HYPER_API_KEY)")
    
    return call("POST", "https://hyper.charm.land/v1/chat/completions",
        {"Authorization": f"Bearer {hyper_key}", "Content-Type": "application/json"},
        {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
        timeout=LONG_TIMEOUT)

def openrouter(prompt: str, model: str = "nvidia/nemotron-3-super-120b-a12b:free", max_tokens: int = 1500) -> requests.Response:
    """OpenRouter API."""
    or_key = _key("OPENROUTER_API_KEY")
    if not or_key:
        raise ProviderAuthError("OpenRouter: No API key configured (OPENROUTER_API_KEY)")
    
    return call("POST", "https://openrouter.ai/api/v1/chat/completions",
        {"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
        {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
        timeout=LONG_TIMEOUT)

def qwen(prompt: str, model: str = "qwen/qwen-2.5-coder-32b-instruct:free", max_tokens: int = 1500) -> requests.Response:
    """Qwen models via OpenRouter free tier."""
    return openrouter(prompt, model=model, max_tokens=max_tokens)

def gemini(prompt: str, model: str = "gemini-2.0-flash", max_tokens: int = 2000) -> requests.Response:
    """Google Gemini API."""
    google_key = _key("GOOGLE_API_KEY")
    if not google_key:
        raise ProviderAuthError("Gemini: No API key configured (GOOGLE_API_KEY)")
    
    return call("POST",
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={google_key}",
        {"Content-Type": "application/json"},
        {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens}},
        timeout=LONG_TIMEOUT)

def deepseek(prompt: str, model: str = "deepseek-chat", max_tokens: int = 2000) -> requests.Response:
    """DeepSeek API."""
    ds_key = _key("DEEPSEEK_API_KEY")
    if not ds_key:
        raise ProviderAuthError("DeepSeek: No API key configured (DEEPSEEK_API_KEY)")
    
    return call("POST", "https://api.deepseek.com/v1/chat/completions",
        {"Authorization": f"Bearer {ds_key}", "Content-Type": "application/json"},
        {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
        timeout=LONG_TIMEOUT)

def mistral(prompt: str, model: str = "open-mistral-nemo", max_tokens: int = 2000) -> requests.Response:
    """Mistral API."""
    mistral_key = _key("MISTRAL_API_KEY")
    if not mistral_key:
        raise ProviderAuthError("Mistral: No API key configured (MISTRAL_API_KEY)")
    
    return call("POST", "https://api.mistral.ai/v1/chat/completions",
        {"Authorization": f"Bearer {mistral_key}", "Content-Type": "application/json"},
        {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
        timeout=LONG_TIMEOUT)

def huggingface(prompt: str, model: str = "meta-llama/Llama-3.2-3B-Instruct", max_tokens: int = 1500) -> requests.Response:
    """Hugging Face Inference API."""
    hf_key = _key("HUGGINGFACE_API_KEY")
    if not hf_key:
        raise ProviderAuthError("HuggingFace: No API key configured (HUGGINGFACE_API_KEY)")
    
    return call("POST",
        f"https://api-inference.huggingface.co/models/{model}",
        {"Authorization": f"Bearer {hf_key}", "Content-Type": "application/json"},
        {"inputs": prompt, "parameters": {"max_new_tokens": max_tokens, "return_full_text": False}},
        timeout=LONG_TIMEOUT)

# ── Response Parsers (with validation) ──

def parse_cloudflare(data: Dict[str, Any]) -> Tuple[Dict[str, int], str]:
    """Parse Cloudflare response - handles both old and new formats."""
    if not isinstance(data, dict):
        raise ProviderResponseError("Cloudflare: Response is not a dict")
    
    result = data.get("result", {})
    
    # New format with choices
    if "choices" in result:
        choices = result.get("choices", [])
        if not choices:
            raise ProviderResponseError("Cloudflare: No choices in response")
        content = choices[0].get("text", "")
        usage = result.get("usage", {})
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0)
        }, content
    
    # Legacy format
    if result and "response" in result:
        tok = result.get("usage", {})
        response = result.get("response", "")
        return {
            "prompt_tokens": tok.get("input_tokens", 0),
            "completion_tokens": tok.get("output_tokens", 0)
        }, response
    
    raise ProviderResponseError("Cloudflare: Unexpected response structure")

def parse_standard(data: Dict[str, Any]) -> Tuple[Dict[str, int], str]:
    """Parse OpenAI-compatible response."""
    if not isinstance(data, dict):
        raise ProviderResponseError("Response is not a dict")
    
    if "choices" not in data:
        raise ProviderResponseError("Response has no 'choices' field")
    
    choices = data.get("choices", [])
    if not choices:
        raise ProviderResponseError("Response has empty 'choices'")
    
    choice = choices[0]
    if "message" not in choice:
        raise ProviderResponseError("Choice has no 'message' field")
    
    message = choice.get("message", {})
    content = message.get("content", "")
    
    usage = data.get("usage", {})
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0)
    }, content

def parse_huggingface(data: Any) -> Tuple[Dict[str, int], str]:
    """Parse Hugging Face Inference API response."""
    # List response (text generation)
    if isinstance(data, list):
        if not data:
            raise ProviderResponseError("HuggingFace: Empty response list")
        content = data[0].get("generated_text", "")
        if not content:
            raise ProviderResponseError("HuggingFace: No generated_text in response")
        return {
            "prompt_tokens": 0,
            "completion_tokens": len(content.split())
        }, content
    
    # Dict response
    if isinstance(data, dict):
        # Try choices format first
        if "choices" in data:
            return parse_standard(data)
        # Try direct generated_text
        if "generated_text" in data:
            content = data["generated_text"]
            return {
                "prompt_tokens": 0,
                "completion_tokens": len(content.split())
            }, content
    
    raise ProviderResponseError(f"HuggingFace: Unexpected response format: {type(data)}")

def parse_gemini(data: Dict[str, Any]) -> Tuple[Dict[str, int], str]:
    """Parse Google Gemini response."""
    if not isinstance(data, dict):
        raise ProviderResponseError("Gemini: Response is not a dict")
    
    if "candidates" not in data or not data["candidates"]:
        raise ProviderResponseError("Gemini: No candidates in response")
    
    candidate = data["candidates"][0]
    if "content" not in candidate or "parts" not in candidate["content"]:
        raise ProviderResponseError("Gemini: Invalid candidate structure")
    
    parts = candidate["content"]["parts"]
    if not parts or "text" not in parts[0]:
        raise ProviderResponseError("Gemini: No text in response parts")
    
    content = parts[0]["text"]
    usage = data.get("usageMetadata", {})
    return {
        "prompt_tokens": usage.get("promptTokenCount", 0),
        "completion_tokens": usage.get("candidatesTokenCount", 0)
    }, content

# ── Provider Registry ──

PROVIDERS = {
    "Groq": (groq, parse_standard),
    "Cloudflare": (cloudflare, parse_cloudflare),
    "Charm Hyper": (hyper, parse_standard),
    "OpenRouter": (openrouter, parse_standard),
    "Qwen": (qwen, parse_standard),
    "HuggingFace": (huggingface, parse_huggingface),
    "Gemini": (gemini, parse_gemini),
    "DeepSeek": (deepseek, parse_standard),
    "Mistral": (mistral, parse_standard),
}
