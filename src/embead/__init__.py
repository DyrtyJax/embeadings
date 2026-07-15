"""Read-only semantic neighborhoods for engineering work trackers."""

from .linear import LinearAdapter
from .provider import Model2VecProvider, provider_readiness
from .surfaces import CodeSurfaceAnalysis, analyze_code_surfaces

__version__ = "0.3.0"

__all__ = [
    "CodeSurfaceAnalysis",
    "LinearAdapter",
    "Model2VecProvider",
    "analyze_code_surfaces",
    "provider_readiness",
]
