"""Plot module for filoma - visualization tools for data-centric ML workflows.

This module provides visualization capabilities for analyzing ML data splits,
detecting data leakage, and validating dataset quality. All functionality is
lazily loaded to maintain fast import times.

Key features:
- Split balance and distribution analysis
- Data leakage detection
- Feature distribution visualization
- File characteristic analysis
- Graceful fallback when plotting libraries unavailable
"""


# Lazy loading to maintain fast imports - plotting functions loaded on demand
def __getattr__(name):
    """Lazy import plotting functions to avoid heavy dependencies at import time."""
    if name == "analyze_splits":
        from .split_analysis import analyze_splits

        return analyze_splits
    elif name == "SplitAnalyzer":
        from .split_analysis import SplitAnalyzer

        return SplitAnalyzer
    elif name == "check_plotting_available":
        from .backends import check_plotting_available

        return check_plotting_available

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# Version info for the plotting module
__version__ = "1.0.0"

# Public API (loaded lazily)
__all__ = [
    "analyze_splits",
    "SplitAnalyzer",
    "check_plotting_available",
]
