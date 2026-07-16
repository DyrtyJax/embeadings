"""Read-only semantic neighborhoods for engineering work trackers."""

from ._version import __version__
from .linear import LinearAdapter
from .provider import Model2VecProvider, provider_readiness
from .surfaces import CodeSurfaceAnalysis, analyze_code_surfaces

__all__ = [
    "CodeSurfaceAnalysis",
    "LinearAdapter",
    "Model2VecProvider",
    "__version__",
    "analyze_code_surfaces",
    "provider_readiness",
]
