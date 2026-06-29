#!/usr/bin/env python3
"""Exception hierarchy for Leverage AI provider errors."""


class ProviderError(Exception):
    """Base exception for all provider-related errors."""
    pass


class ProviderTimeout(ProviderError):
    """Request timed out."""
    pass


class ProviderConnectionError(ProviderError):
    """Network/connection issue."""
    pass


class ProviderAuthError(ProviderError):
    """Authentication failed - bad key or no key."""
    pass


class ProviderRateLimit(ProviderError):
    """Rate limit hit (429) or quota exceeded (402)."""
    pass


class ProviderResponseError(ProviderError):
    """Response parsing failed or invalid structure."""
    pass


class ProviderNotAvailable(ProviderError):
    """Provider explicitly marked as unavailable."""
    pass
