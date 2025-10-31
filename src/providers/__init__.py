"""
MPI Providers Package

This package contains all MPI provider implementations following a standardized interface.

Available Providers:
- VeratoProvider: Verato external API provider
- InternalMPIProvider: Internal probabilistic matching provider
- HybridMPIProvider: Combined provider with multiple strategies

All providers implement the BaseMPIProvider interface for consistent integration.
"""

from .base_provider import BaseMPIProvider, MPIResult, ProviderConfig
from .verato_provider import VeratoProvider, VeratoProviderConfig
from .internal import InternalMPIProvider, InternalProviderConfig
from .hybrid import HybridMPIProvider, HybridProviderConfig, HybridStrategy

# Legacy compatibility - keep the original verato module available
from .verato import VeratoModule, VeratoConfig

__all__ = [
    # Base classes
    'BaseMPIProvider',
    'MPIResult',
    'ProviderConfig',

    # Provider implementations
    'VeratoProvider',
    'VeratoProviderConfig',
    'InternalMPIProvider',
    'InternalProviderConfig',
    'HybridMPIProvider',
    'HybridProviderConfig',
    'HybridStrategy',

    # Legacy compatibility
    'VeratoModule',
    'VeratoConfig'
]

# Provider registry for dynamic loading
PROVIDER_REGISTRY = {
    'verato': VeratoProvider,
    'internal': InternalMPIProvider,
    'hybrid': HybridMPIProvider
}

def get_provider_class(provider_name: str):
    """
    Get provider class by name

    Args:
        provider_name: Name of the provider ('verato', 'internal', 'hybrid')

    Returns:
        Provider class

    Raises:
        ValueError: If provider name is not recognized
    """
    provider_name = provider_name.lower()

    if provider_name not in PROVIDER_REGISTRY:
        available = ', '.join(PROVIDER_REGISTRY.keys())
        raise ValueError(f"Unknown provider '{provider_name}'. Available providers: {available}")

    return PROVIDER_REGISTRY[provider_name]

def create_provider(provider_name: str, config=None, **kwargs):
    """
    Create provider instance by name

    Args:
        provider_name: Name of the provider
        config: Provider-specific configuration object
        **kwargs: Additional arguments passed to provider constructor

    Returns:
        Provider instance
    """
    provider_class = get_provider_class(provider_name)
    return provider_class(config=config, **kwargs)