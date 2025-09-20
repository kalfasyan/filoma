"""Base classes for image profilers.

This module defines the `BaseImageProfiler` abstract base class and
helpers used by concrete image profiler implementations.
"""

from abc import ABC, abstractmethod
from typing import Union

from rich.console import Console
from rich.table import Table

from .image_profiler import ImageReport


class BaseImageProfiler(ABC):
    """Abstract base for image profilers exposing a common API."""

    def __init__(self):
        """Initialize the profiler with a Rich console for reporting."""
        self.console = Console()

    @abstractmethod
    def probe(self, path):
        """Perform analysis of the file at `path` and return an ImageReport.

        Concrete implementations must return an :class:`ImageReport`.
        """
        pass

    def print_report(self, report: Union[dict, "ImageReport"]):
        """Print a formatted report of analysis results.

        Accepts either a mapping or an :class:`ImageReport` instance.
        """
        # Support both dicts and ImageReport instances
        if hasattr(report, "to_dict"):
            data = report.to_dict()
        else:
            data = dict(report)

        table = Table(title=f"Image Analysis Report: {data.get('path', 'Unknown')}")
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        for key, value in data.items():
            if key != "path":  # Don't duplicate the path in the table
                table.add_row(str(key), str(value))

        self.console.print(table)
