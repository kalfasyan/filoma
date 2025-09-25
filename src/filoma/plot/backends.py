"""Plotting backend management for filoma.plot module.

Provides a unified interface for plotting with matplotlib/seaborn while
gracefully falling back to text-based summaries when plotting libraries
are not available.
"""

from typing import Any, Dict, List, Optional

from loguru import logger

# Global flag to track if we've checked for plotting availability
_plotting_checked = False
_plotting_available = False
_missing_packages = []


def check_plotting_available() -> Dict[str, Any]:
    """Check if matplotlib and seaborn are available for plotting.

    Returns:
        Dict with availability status and missing packages.

    """
    global _plotting_checked, _plotting_available, _missing_packages

    if _plotting_checked:
        return {"available": _plotting_available, "missing": _missing_packages}

    missing = []

    try:
        import matplotlib.pyplot as plt  # noqa: F401
    except ImportError:
        missing.append("matplotlib")

    try:
        import seaborn  # noqa: F401
    except ImportError:
        missing.append("seaborn")

    _plotting_checked = True
    _plotting_available = len(missing) == 0
    _missing_packages = missing

    return {"available": _plotting_available, "missing": missing}


class PlottingBackend:
    """Unified plotting backend that handles matplotlib/seaborn with graceful fallback."""

    def __init__(self):
        """Initialize the plotting backend and check for available libraries."""
        self._status = check_plotting_available()
        if not self._status["available"]:
            logger.warning(
                f"Plotting libraries not available: {self._status['missing']}. "
                f"Install with: pip install 'filoma[viz]' for full visualization. "
                f"Text summaries will be provided instead."
            )

    @property
    def available(self) -> bool:
        """Check if plotting backend is available."""
        return self._status["available"]

    @property
    def missing_packages(self) -> List[str]:
        """Get list of missing packages."""
        return self._status["missing"]

    def setup_matplotlib(self) -> Optional[Any]:
        """Set up matplotlib with sensible defaults for filoma plots."""
        if not self.available:
            return None

        try:
            import matplotlib.pyplot as plt
            import seaborn as sns

            # Set up seaborn style
            sns.set_style("whitegrid")
            sns.set_palette("husl")

            # Configure matplotlib
            plt.rcParams["figure.figsize"] = (10, 6)
            plt.rcParams["font.size"] = 11
            plt.rcParams["axes.titlesize"] = 14
            plt.rcParams["axes.labelsize"] = 12

            return plt, sns

        except ImportError as e:
            logger.error(f"Failed to set up matplotlib: {e}")
            return None

    def create_figure(self, figsize: tuple = (10, 6), **kwargs):
        """Create a matplotlib figure with consistent styling."""
        if not self.available:
            return None

        try:
            plt, sns = self.setup_matplotlib()
            if plt is None:
                return None

            fig, ax = plt.subplots(figsize=figsize, **kwargs)
            return fig, ax

        except Exception as e:
            logger.error(f"Failed to create figure: {e}")
            return None

    def save_figure(self, fig, filepath: str, **kwargs):
        """Save figure with consistent settings."""
        if not self.available or fig is None:
            return False

        try:
            default_kwargs = {"dpi": 150, "bbox_inches": "tight", "facecolor": "white"}
            default_kwargs.update(kwargs)

            fig.savefig(filepath, **default_kwargs)
            return True

        except Exception as e:
            logger.error(f"Failed to save figure to {filepath}: {e}")
            return False

    def show_text_fallback(self, message: str) -> str:
        """Display text-based fallback when plotting is not available."""
        fallback_msg = f"""
╭─ Visualization Not Available ─╮
│ {message:<30} │
│                                │
│ Install plotting dependencies: │
│ pip install 'filoma[viz]'      │
╰────────────────────────────────╯
"""
        print(fallback_msg)
        return fallback_msg


# Global backend instance
backend = PlottingBackend()
