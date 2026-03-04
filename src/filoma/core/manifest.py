"""Manifest generation and validation for filoma.

Provides tools to create manifests of directory structures with SHA-256 hash-based
integrity verification. Manifests include file hashes, sizes, metadata, and data lineage.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from loguru import logger
from rich.console import Console
from rich.table import Table

from ..dataframe import DataFrame


class Manifest:
    """Handles generation and validation of dataset manifests."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize Manifest handler."""
        self.console = console or Console()

    def generate(self, df: DataFrame, compute_hashes: bool = True) -> Dict[str, Any]:
        """Generate a manifest dictionary from a filoma.DataFrame.

        The manifest includes file metadata (path, size, modified_time, sha256)
        and the data lineage history of the DataFrame.
        """
        # Ensure we have the required columns
        required_cols = {"size_bytes", "modified_time", "sha256"}
        missing_cols = required_cols - set(df.columns)

        if missing_cols or (compute_hashes and df.df["sha256"].null_count() > 0):
            logger.info(f"Enriching DataFrame for manifest generation (compute_hashes={compute_hashes})")
            # We use a copy to avoid mutating the original df unless desired by caller
            df = df.add_file_stats_cols(compute_hash=compute_hashes)

        # Build manifest structure
        manifest_data = {
            "version": "1.0",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "lineage": df.lineage,
            "summary": {
                "total_files": len(df),
                "total_size_bytes": df.df["size_bytes"].sum() if "size_bytes" in df.df.columns else 0,
            },
            # We'll store the core metadata as a list of dicts
            "files": df.df.select(["path", "size_bytes", "modified_time", "sha256"]).to_dicts(),
        }

        return manifest_data

    def save(self, manifest_data: Dict[str, Any], path: Union[str, Path]) -> None:
        """Save manifest data to a JSON file."""
        path = Path(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        logger.success(f"Manifest saved to {path}")

    def load(self, path: Union[str, Path]) -> Dict[str, Any]:
        """Load manifest data from a JSON file."""
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def verify(self, manifest_path: Union[str, Path], root_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """Verify a directory against a manifest.

        Checks if files exist, if their sizes match, and if their hashes are correct.
        Returns a report of discrepancies.
        """
        data = self.load(manifest_path)
        files = data.get("files", [])
        manifest_root = Path(manifest_path).parent

        # If no root_path provided, assume files are relative to manifest location
        root = Path(root_path) if root_path else manifest_root

        logger.info(f"Verifying {len(files)} files against manifest {manifest_path}")

        results = {
            "matched": [],
            "missing": [],
            "size_mismatch": [],
            "hash_mismatch": [],
            "extra": [],
        }

        from ..files.file_profiler import FileProfiler

        profiler = FileProfiler()

        for f_info in files:
            rel_path = f_info["path"]
            # If the path in manifest is absolute, use it; otherwise resolve relative to root
            p = Path(rel_path)
            if not p.is_absolute():
                p = root / rel_path

            if not p.exists():
                results["missing"].append(rel_path)
                continue

            # Check size and hash
            try:
                # We probe without hash first for speed
                filo = profiler.probe(str(p), compute_hash=False)
                if filo.size != f_info["size_bytes"]:
                    results["size_mismatch"].append(rel_path)
                    continue

                # Now check hash
                filo = profiler.probe(str(p), compute_hash=True)
                if filo.sha256 != f_info["sha256"]:
                    results["hash_mismatch"].append(rel_path)
                    continue

                results["matched"].append(rel_path)
            except Exception as e:
                logger.error(f"Error verifying {rel_path}: {e}")
                results["missing"].append(rel_path)

        # Summary of results
        total = len(files)
        matched = len(results["matched"])

        if matched == total:
            logger.success(f"Verification successful: All {total} files match.")
        else:
            logger.warning(
                f"Verification incomplete: {matched}/{total} matched. "
                f"{len(results['missing'])} missing, "
                f"{len(results['size_mismatch'])} size mismatches, "
                f"{len(results['hash_mismatch'])} hash mismatches."
            )

        return results

    def print_report(self, results: Dict[str, Any], show_files: bool = True, max_files: int = 10):
        """Print a summary table of verification results.

        Args:
            results: Verification results dictionary
            show_files: If True, show file paths for mismatches (default: True)
            max_files: Maximum number of file paths to show per category (default: 10)

        """
        table = Table(title="Manifest Verification Report")
        table.add_column("Category", style="bold cyan")
        table.add_column("Count", style="white")
        table.add_column("Status", style="bold")

        table.add_row("Matched", str(len(results["matched"])), "[green]OK[/green]")
        table.add_row("Missing", str(len(results["missing"])), "[red]FAIL[/red]" if results["missing"] else "[green]OK[/green]")
        table.add_row("Size Mismatch", str(len(results["size_mismatch"])), "[red]FAIL[/red]" if results["size_mismatch"] else "[green]OK[/green]")
        table.add_row("Hash Mismatch", str(len(results["hash_mismatch"])), "[red]FAIL[/red]" if results["hash_mismatch"] else "[green]OK[/green]")

        self.console.print(table)

        # Show file details for mismatches if requested and there are any
        if show_files:
            if results["missing"]:
                self.console.print("\n[red]Missing Files:[/red]")
                for path in results["missing"][:max_files]:
                    self.console.print(f"  • {path}")
                if len(results["missing"]) > max_files:
                    self.console.print(f"  ... and {len(results['missing']) - max_files} more")

            if results["size_mismatch"]:
                self.console.print("\n[yellow]Size Mismatches:[/yellow]")
                for path in results["size_mismatch"][:max_files]:
                    self.console.print(f"  • {path}")
                if len(results["size_mismatch"]) > max_files:
                    self.console.print(f"  ... and {len(results['size_mismatch']) - max_files} more")

            if results["hash_mismatch"]:
                self.console.print("\n[red]Hash Mismatches:[/red]")
                for path in results["hash_mismatch"][:max_files]:
                    self.console.print(f"  • {path}")
                if len(results["hash_mismatch"]) > max_files:
                    self.console.print(f"  ... and {len(results['hash_mismatch']) - max_files} more")
