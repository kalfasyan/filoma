from abc import ABC, abstractmethod
from typing import Union

from rich.console import Console
from rich.table import Table

from .image_profiler import ImageReport


class BaseImageProfiler(ABC):
    def __init__(self):
        self.console = Console()

    @abstractmethod
    def probe(self, path):
        """Perform analysis and return an ImageReport."""
        pass

    def print_report(self, report: Union[dict, "ImageReport"]):
        """Print a formatted report of the analysis.

        Accepts either a dict or an `ImageReport` dataclass.
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
