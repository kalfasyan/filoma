"""Utility functions for the plot module."""

from typing import Any, Dict, List, Optional, Tuple, Union

import polars as pl
from rich.console import Console
from rich.table import Table

console = Console()


def format_split_summary(splits: Tuple, split_names: Optional[List[str]] = None) -> Dict:
    """Format a summary of split data for display.

    Args:
        splits: Tuple of DataFrames (train, val, test)
        split_names: Optional names for splits

    Returns:
        Dictionary with split summary information

    """
    if split_names is None:
        split_names = [f"Split {i + 1}" for i in range(len(splits))]

    summary = {"total_samples": sum(len(df) for df in splits), "splits": []}

    for i, (split_df, name) in enumerate(zip(splits, split_names)):
        split_info = {"name": name, "count": len(split_df), "percentage": len(split_df) / summary["total_samples"] * 100, "index": i}
        summary["splits"].append(split_info)

    return summary


def print_split_summary(splits: Tuple, split_names: Optional[List[str]] = None) -> None:
    """Print a formatted summary of splits using rich tables.

    Args:
        splits: Tuple of DataFrames (train, val, test)
        split_names: Optional names for splits

    """
    summary = format_split_summary(splits, split_names)

    table = Table(title="Split Summary", show_header=True, header_style="bold magenta")
    table.add_column("Split", style="cyan", width=12)
    table.add_column("Count", justify="right", style="green")
    table.add_column("Percentage", justify="right", style="yellow")

    for split_info in summary["splits"]:
        table.add_row(split_info["name"], f"{split_info['count']:,}", f"{split_info['percentage']:.1f}%")

    # Add total row
    table.add_row("[bold]Total[/bold]", f"[bold]{summary['total_samples']:,}[/bold]", "[bold]100.0%[/bold]")

    console.print(table)


def extract_feature_values(splits: Tuple, feature: Union[str, List[str]], split_names: Optional[List[str]] = None) -> Dict:
    """Extract feature values from splits for analysis.

    Args:
        splits: Tuple of DataFrames
        feature: Feature column name(s) to analyze
        split_names: Optional names for splits

    Returns:
        Dictionary with feature analysis data

    """
    if split_names is None:
        split_names = [f"Split {i + 1}" for i in range(len(splits))]

    feature_data = {"feature": feature, "splits": {}, "all_values": set(), "split_names": split_names}

    # Handle single feature or multiple features
    if isinstance(feature, str):
        feature_cols = [feature]
    else:
        feature_cols = list(feature)

    for split_df, name in zip(splits, split_names):
        # Check if all feature columns exist
        missing_cols = [col for col in feature_cols if col not in split_df.columns]
        if missing_cols:
            continue

        if len(feature_cols) == 1:
            # Single feature
            values = split_df[feature_cols[0]].to_list()
        else:
            # Multiple features - combine them
            values = []
            for row in split_df.select(feature_cols).iter_rows():
                combined_value = "_".join(str(v) for v in row)
                values.append(combined_value)

        unique_values = set(values)
        feature_data["splits"][name] = {"values": values, "unique_values": unique_values, "count": len(values), "unique_count": len(unique_values)}
        feature_data["all_values"].update(unique_values)

    return feature_data


def detect_distribution_issues(feature_data: Dict) -> Dict:
    """Detect feature distribution inconsistencies across splits.

    This detects poor splitting strategies that could hurt generalization
    by identifying uneven feature coverage, split-exclusive values, and
    missing feature representation across train/validation/test splits.

    Note: This does NOT detect actual data leakage (which requires
    domain knowledge and temporal/grouping analysis).

    Args:
        feature_data: Feature analysis data from extract_feature_values

    Returns:
        Dictionary with distribution analysis results

    """
    splits_data = feature_data["splits"]
    all_unique_values = feature_data["all_values"]

    distribution_analysis = {
        "has_distribution_issues": False,
        "missing_values": {},
        "exclusive_to_split": {},
        "common_values": set(all_unique_values),
        "coverage_analysis": {},
    }

    # Find values exclusive to each split and missing from others
    for split_name, split_data in splits_data.items():
        split_unique = split_data["unique_values"]

        # Values missing from this split
        missing = all_unique_values - split_unique
        if missing:
            distribution_analysis["missing_values"][split_name] = missing
            distribution_analysis["has_distribution_issues"] = True

        # Values exclusive to this split
        exclusive_to_this_split = split_unique.copy()
        for other_name, other_data in splits_data.items():
            if other_name != split_name:
                exclusive_to_this_split -= other_data["unique_values"]

        if exclusive_to_this_split:
            distribution_analysis["exclusive_to_split"][split_name] = exclusive_to_this_split

        # Coverage analysis
        coverage_pct = len(split_unique) / len(all_unique_values) * 100
        distribution_analysis["coverage_analysis"][split_name] = {
            "unique_count": len(split_unique),
            "total_possible": len(all_unique_values),
            "coverage_percentage": coverage_pct,
        }

        # Update common values (intersection)
        distribution_analysis["common_values"] &= split_unique

    return distribution_analysis


def safe_get_column(df: Union[pl.DataFrame, Any], col_name: str):
    """Safely get a column from a DataFrame, handling both Polars and filoma wrappers.

    Args:
        df: DataFrame to extract from
        col_name: Column name to extract

    Returns:
        Column data if found, None otherwise

    """
    try:
        # Handle filoma DataFrame wrapper
        if hasattr(df, "df"):
            actual_df = df.df
        else:
            actual_df = df

        if col_name in actual_df.columns:
            return actual_df[col_name].to_list()
        else:
            return None
    except Exception:
        return None
