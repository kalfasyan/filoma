from abc import ABC, abstractmethod

from rich.console import Console
from rich.table import Table


class BaseImageProfiler(ABC):
    def __init__(self):
        self.console = Console()

    @abstractmethod
    def analyze(self, path):
        """Perform analysis and return a report (dict or custom object)."""
        pass

    def print_report(self, report: dict):
        """Print a formatted report of the analysis."""
        table = Table(title=f"Image Analysis Report: {report.get('path', 'Unknown')}")
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        for key, value in report.items():
            if key != "path":  # Don't duplicate the path in the table
                table.add_row(str(key), str(value))

        self.console.print(table)
