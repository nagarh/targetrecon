"""TargetRecon — Drug target intelligence aggregator."""
from __future__ import annotations

__version__ = "0.1.12"

from targetrecon.core import recon, recon_async

__all__ = ["recon", "recon_async", "__version__"]
