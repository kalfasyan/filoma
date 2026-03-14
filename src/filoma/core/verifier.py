"""Dataset verification utilities."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image
from rich.console import Console
from rich.table import Table

from filoma import dedup
from filoma.core.manifest import Manifest
from filoma.core.snapshot import verify as verify_snapshot


class DatasetVerifier:
    """Orchestrator for dataset integrity and quality checks."""

    def __init__(self, root_dir: str):
        """Initialize the DatasetVerifier with the root directory to verify."""
        self.root_dir = Path(root_dir)
        self.console = Console()
        self.results = {}

    def run_all(self, label_source: str = "auto"):
        """Run all verification checks."""
        self.results = {
            "integrity": self.check_integrity(),
            "dimensions": self.check_dimensions(),
            "duplicates": self.find_duplicates(),
            "class_balance": self.check_class_balance(label_source=label_source),
            "leakage": self.check_cross_split_leakage(),
            "pixel_stats": self.check_pixel_stats(),
        }
        return self.results

    def check_integrity(self) -> Dict[str, Any]:
        """Check for zero-byte files and corrupt images."""
        failed_files = []
        for path in self.root_dir.rglob("*"):
            if path.is_file():
                if path.stat().st_size == 0:
                    failed_files.append({"path": str(path), "reason": "zero_byte"})
                    continue
                if path.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                    except Exception:
                        failed_files.append({"path": str(path), "reason": "corrupt_or_unsupported"})
        return {"failed_files": failed_files}

    def check_dimensions(self) -> Dict[str, Any]:
        """Check for dimension consistency."""
        from collections import Counter

        dimensions = []
        for path in self.root_dir.rglob("*"):
            if path.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]:
                try:
                    with Image.open(path) as img:
                        dimensions.append(img.size)
                except Exception:
                    pass

        if not dimensions:
            return {"status": "no_images_found"}

        counts = Counter(dimensions)
        most_common_dim, _ = counts.most_common(1)[0]
        outliers = [dim for dim in dimensions if dim != most_common_dim]

        return {
            "most_common_dimension": most_common_dim,
            "outlier_count": len(outliers),
            "outlier_percentage": (len(outliers) / len(dimensions)) * 100,
        }

    def find_duplicates(self) -> Dict[str, Any]:
        """Find near-duplicate images."""
        hashes = {}
        duplicates = []
        for path in self.root_dir.rglob("*"):
            if path.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]:
                try:
                    h = dedup.dhash_image(str(path))
                    if h in hashes:
                        duplicates.append((str(path), hashes[h]))
                    else:
                        hashes[h] = str(path)
                except Exception:
                    pass

        return {"duplicate_count": len(duplicates), "duplicates": duplicates}

    def check_class_balance(self, label_source: str = "auto") -> Dict[str, Any]:
        """Check class balance from CSV files."""
        from collections import Counter

        import pandas as pd

        counts = Counter()

        # 1. Try CSV
        if label_source in ["auto", "csv"]:
            for path in self.root_dir.rglob("*.csv"):
                try:
                    df = pd.read_csv(path)
                    # Check for common column names: 'label', 'class', etc.
                    # In Weeds-3, it's 'filename, Weeds' where 'Weeds' is the class
                    cols = [c for c in df.columns if c.strip() != "filename"]
                    if cols:
                        target_col = cols[0]
                        counts.update(df[target_col].value_counts().to_dict())
                except Exception:
                    pass

        # 2. If no csv, fallback to directory structure
        if not counts and label_source in ["auto", "folder"]:
            for path in self.root_dir.rglob("*"):
                if path.is_file() and path.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]:
                    # Assume structure: root/split/class/filename or root/class/filename
                    # We'll take the parent directory name as the class
                    counts[path.parent.name] += 1

        return {"class_distribution": dict(counts)}

    def check_cross_split_leakage(self) -> Dict[str, Any]:
        """Identify files that appear in multiple split subdirectories."""
        from collections import defaultdict

        files_per_split = defaultdict(set)
        for path in self.root_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]:
                # Assume dir structure root/split/filename
                split = path.parent.name
                if split in ["train", "valid", "test"]:
                    files_per_split[split].add(path.name)

        leaked_files = defaultdict(list)
        splits = list(files_per_split.keys())
        for i, split1 in enumerate(splits):
            for split2 in splits[i + 1 :]:
                common = files_per_split[split1].intersection(files_per_split[split2])
                for file in common:
                    leaked_files[file].append((split1, split2))

        return {"leaked_files": dict(leaked_files)}

    def check_pixel_stats(self) -> Dict[str, Any]:
        """Detect images with anomalous statistics (e.g., all black/white)."""
        import numpy as np

        anomalous_files = []
        for path in self.root_dir.rglob("*"):
            if path.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]:
                try:
                    with Image.open(path) as img:
                        arr = np.array(img)
                        if arr.std() < 0.1:
                            anomalous_files.append(str(path))
                except Exception:
                    pass

        return {"anomalous_files": anomalous_files}

    def print_summary(self):
        """Print a formatted summary of the verification results."""
        if not self.results:
            self.run_all()

        table = Table(title="Dataset Verification Summary")
        table.add_column("Check", style="cyan")
        table.add_column("Status", style="magenta")

        # Integrity
        integrity = self.results["integrity"]
        table.add_row("Integrity", f"{len(integrity['failed_files'])} issues found")

        # Dimensions
        dims = self.results["dimensions"]
        if "status" in dims:
            table.add_row("Dimensions", dims["status"])
        else:
            table.add_row("Dimensions", f"{dims['outlier_count']} outliers ({dims['outlier_percentage']:.2f}%)")

        # Duplicates
        dups = self.results["duplicates"]
        table.add_row("Duplicates", f"{dups['duplicate_count']} found")

        # Class Balance
        balance = self.results["class_balance"]
        dist = balance.get("class_distribution", {})
        table.add_row("Class Balance", f"{len(dist)} classes found")

        # Leakage
        leakage = self.results["leakage"]
        table.add_row("Leakage", f"{len(leakage['leaked_files'])} leaked files")

        # Pixel Stats
        pixel = self.results["pixel_stats"]
        table.add_row("Anomalous", f"{len(pixel['anomalous_files'])} images")

        self.console.print(table)

    def export_report(self, path: str, format: str = "json"):
        """Export the verification results to a file."""
        if format == "json":
            with open(path, "w") as f:
                json.dump(self.results, f, indent=4)
        else:
            raise ValueError(f"Unsupported format: {format}")


def verify_dataset(
    reference_file: str,
    target_path: Optional[str] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Unified verification interface. Detects if reference is a Snapshot or Manifest."""
    ref_path = Path(reference_file)
    with open(ref_path, "r") as f:
        data = json.load(f)

    # Detect type
    if "lineage" in data:
        # It's a manifest
        manifest = Manifest()
        return manifest.verify(reference_file, root_path=target_path)
    else:
        # Assuming snapshot
        from typing import Literal, cast

        return verify_snapshot(
            reference_file,
            target_path=target_path,
            mode=cast(Optional[Literal["fast", "deep", "full"]], mode),
        )
