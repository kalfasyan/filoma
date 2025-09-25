"""Split analysis and visualization for filoma ML workflows.

This module provides the main SplitAnalyzer class that wraps around
ml.split_data results to provide visualization and validation capabilities.
"""

from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger

from .backends import backend
from .utils import (
    detect_distribution_issues,
    extract_feature_values,
    format_split_summary,
    print_split_summary,
    safe_get_column,
)


class SplitAnalyzer:
    """Analyze and visualize ML data splits for data-centric workflows.

    This class wraps around the results of filoma.ml.split_data to provide
    comprehensive analysis and visualization capabilities without modifying
    the existing ML splitting functionality.
    """

    def __init__(
        self,
        splits: Tuple,
        split_names: Optional[List[str]] = None,
        feature: Optional[Union[str, List[str]]] = None,
        original_data: Optional[Any] = None,
    ):
        """Initialize the SplitAnalyzer.

        Args:
            splits: Tuple of DataFrames from ml.split_data
            split_names: Optional names for the splits
            feature: Feature(s) used for splitting
            original_data: Original DataFrame before splitting

        """
        self.splits = splits
        self.split_names = split_names or ["Train", "Validation", "Test"]
        self.feature = feature
        self.original_data = original_data

        # Ensure we have the right number of names
        if len(self.split_names) != len(self.splits):
            self.split_names = [f"Split {i + 1}" for i in range(len(self.splits))]

        # Cache for expensive computations
        self._summary_cache = None
        self._feature_data_cache = None
        self._distribution_analysis_cache = None

    def summary(self) -> Dict:
        """Get a statistical summary of the splits.

        Returns:
            Dictionary with split summary statistics

        """
        if self._summary_cache is None:
            self._summary_cache = format_split_summary(self.splits, self.split_names)
        return self._summary_cache

    def print_summary(self) -> None:
        """Print a formatted summary of the splits using rich tables."""
        print_split_summary(self.splits, self.split_names)

    def balance(self, show_plot: bool = True) -> Dict:
        """Analyze split balance and optionally display visualization.

        Args:
            show_plot: Whether to display the balance plot

        Returns:
            Dictionary with balance analysis results

        """
        summary = self.summary()

        if show_plot and backend.available:
            return self._plot_balance(summary)
        elif show_plot:
            # Text fallback
            backend.show_text_fallback("Split balance visualization")
            self.print_summary()

        return summary

    def feature_distribution(self, show_plot: bool = True) -> Dict:
        """Analyze feature distribution across splits.

        Args:
            show_plot: Whether to display the distribution plot

        Returns:
            Dictionary with feature distribution analysis

        """
        if self.feature is None:
            logger.warning("No feature specified for distribution analysis")
            return {}

        if self._feature_data_cache is None:
            self._feature_data_cache = extract_feature_values(self.splits, self.feature, self.split_names)

        if show_plot and backend.available:
            return self._plot_feature_distribution(self._feature_data_cache)
        elif show_plot:
            backend.show_text_fallback("Feature distribution visualization")
            self._print_feature_summary(self._feature_data_cache)

        return self._feature_data_cache

    def distribution_analysis(self, show_plot: bool = True) -> Dict:
        """Analyze feature distribution consistency across splits.

        This method detects distribution issues that could hurt generalization,
        such as uneven feature coverage, split-exclusive values, and missing
        feature representation. This is NOT data leakage detection.

        Args:
            show_plot: Whether to display distribution analysis plots

        Returns:
            Dictionary with distribution analysis results

        """
        if self.feature is None:
            logger.warning("No feature specified for leakage analysis")
            return {}

        # Get feature data if not cached
        if self._feature_data_cache is None:
            self._feature_data_cache = extract_feature_values(self.splits, self.feature, self.split_names)

        if self._distribution_analysis_cache is None:
            self._distribution_analysis_cache = detect_distribution_issues(self._feature_data_cache)

        if show_plot and backend.available:
            return self._plot_distribution_analysis(self._distribution_analysis_cache)
        elif show_plot:
            backend.show_text_fallback("Distribution analysis visualization")
            self._print_distribution_summary(self._distribution_analysis_cache)

        return self._distribution_analysis_cache

    def leakage_check(self, show_plot: bool = True) -> Dict:
        """Legacy method name - use distribution_analysis() instead.

        This method has been renamed to better reflect its purpose.
        It analyzes distribution issues, not actual data leakage.
        """
        logger.warning("leakage_check() is deprecated. Use distribution_analysis() instead.")
        return self.distribution_analysis(show_plot=show_plot)

    def characteristics(self, columns: Optional[List[str]] = None, show_plot: bool = True) -> Dict:
        """Analyze file characteristics across splits.

        Args:
            columns: Specific columns to analyze (e.g., 'size', 'extension')
            show_plot: Whether to display characteristic plots

        Returns:
            Dictionary with characteristics analysis

        """
        # Default columns to analyze
        if columns is None:
            columns = ["size", "extension", "depth"] if hasattr(self.splits[0], "columns") else []

        char_data = {}
        for col in columns:
            col_data = {}
            for split, name in zip(self.splits, self.split_names):
                values = safe_get_column(split, col)
                if values is not None:
                    col_data[name] = values

            if col_data:
                char_data[col] = col_data

        if show_plot and backend.available and char_data:
            return self._plot_characteristics(char_data)
        elif show_plot and char_data:
            backend.show_text_fallback("File characteristics visualization")
            self._print_characteristics_summary(char_data)

        return char_data

    def validate(self) -> Dict:
        """Run comprehensive validation checks on the splits.

        Returns:
            Dictionary with all validation results

        """
        validation_results = {"summary": self.summary(), "balance_ok": True, "distribution_issues": False, "issues": []}

        # Check balance (warn if any split is < 5% or > 80%)
        for split_info in validation_results["summary"]["splits"]:
            pct = split_info["percentage"]
            if pct < 5:
                validation_results["balance_ok"] = False
                validation_results["issues"].append(f"{split_info['name']} has very small size: {pct:.1f}%")
            elif pct > 80:
                validation_results["balance_ok"] = False
                validation_results["issues"].append(f"{split_info['name']} is very large: {pct:.1f}%")

        # Check for distribution issues if feature is available
        if self.feature is not None:
            distribution_results = self.distribution_analysis(show_plot=False)
            if distribution_results.get("has_distribution_issues", False):
                validation_results["distribution_issues"] = True
                validation_results["issues"].append("Distribution issues detected between splits")

        return validation_results

    def _assess_balance_quality(self, percentages: List[float]) -> str:
        """Assess the quality of split balance."""
        if not percentages:
            return "Unknown"

        # Check for very unbalanced splits
        min_pct, max_pct = min(percentages), max(percentages)

        if min_pct < 5:
            return "Poor (very small split)"
        elif max_pct > 80:
            return "Poor (very large split)"
        elif max_pct - min_pct > 40:
            return "Fair (unbalanced)"
        elif max_pct - min_pct > 20:
            return "Good"
        else:
            return "Excellent"

    def _plot_balance(self, summary: Dict) -> Dict:
        """Create balance visualization using matplotlib."""
        try:
            fig, ax = backend.create_figure(figsize=(10, 6))
            if fig is None:
                return summary

            plt, sns = backend.setup_matplotlib()
            if plt is None:
                return summary

            split_names = [s["name"] for s in summary["splits"]]
            counts = [s["count"] for s in summary["splits"]]
            percentages = [s["percentage"] for s in summary["splits"]]

            # Create bar plot with custom colors
            colors = sns.color_palette("husl", len(split_names))
            bars = ax.bar(split_names, counts, color=colors, alpha=0.8, edgecolor="white", linewidth=1.2)

            # Add percentage labels on bars
            for bar, pct in zip(bars, percentages):
                height = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    height + height * 0.01,
                    f"{pct:.1f}%",
                    ha="center",
                    va="bottom",
                    fontweight="bold",
                    fontsize=11,
                )

            # Styling improvements
            ax.set_title("Split Balance Analysis", fontsize=16, fontweight="bold", pad=20)
            ax.set_ylabel("Number of Samples", fontsize=12)
            ax.set_xlabel("Split", fontsize=12)

            # Add grid for easier reading
            ax.grid(axis="y", alpha=0.3, linestyle="--")
            ax.set_axisbelow(True)

            # Format y-axis to show comma separators for large numbers
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:,.0f}"))

            # Add total count and balance quality assessment
            total_samples = summary["total_samples"]
            balance_quality = self._assess_balance_quality(percentages)

            plt.figtext(0.5, 0.02, f"Total samples: {total_samples:,} | Balance quality: {balance_quality}", ha="center", fontsize=10, style="italic")

            plt.tight_layout()
            plt.show()

            return summary

        except Exception as e:
            logger.error(f"Failed to create balance plot: {e}")
            return summary

    def _plot_feature_distribution(self, feature_data: Dict) -> Dict:
        """Create feature distribution visualization."""
        try:
            fig, axes = backend.create_figure(figsize=(15, 5), ncols=len(feature_data["splits"]))
            if fig is None:
                return feature_data

            plt, sns = backend.setup_matplotlib()
            if plt is None:
                return feature_data

            # If only one split, make axes iterable
            if len(feature_data["splits"]) == 1:
                axes = [axes]

            feature_name = feature_data["feature"]
            if isinstance(feature_name, list):
                feature_name = "+".join(feature_name)

            for i, (split_name, split_data) in enumerate(feature_data["splits"].items()):
                ax = axes[i]

                # Get value counts
                values = split_data["values"]
                unique_values = list(set(values))
                value_counts = {val: values.count(val) for val in unique_values}

                # Sort by count for better visualization
                sorted_items = sorted(value_counts.items(), key=lambda x: x[1], reverse=True)

                # Limit to top 10 values if too many
                if len(sorted_items) > 10:
                    sorted_items = sorted_items[:10]
                    ax.set_title(f"{split_name}\n(Top 10 values)", fontsize=12, fontweight="bold")
                else:
                    ax.set_title(f"{split_name}", fontsize=12, fontweight="bold")

                if sorted_items:
                    labels, counts = zip(*sorted_items)

                    # Choose plot type based on data characteristics
                    if len(sorted_items) <= 5:
                        # Bar plot for few categories
                        bars = ax.bar(range(len(labels)), counts, color=sns.color_palette("husl", len(labels)), alpha=0.8)
                        ax.set_xticks(range(len(labels)))
                        ax.set_xticklabels(labels, rotation=45, ha="right")

                        # Add count labels on bars
                        for bar in bars:
                            height = bar.get_height()
                            ax.text(
                                bar.get_x() + bar.get_width() / 2.0, height + height * 0.01, f"{int(height)}", ha="center", va="bottom", fontsize=10
                            )
                    else:
                        # Horizontal bar plot for many categories
                        ax.barh(range(len(labels)), counts, color=sns.color_palette("husl", len(labels)), alpha=0.8)
                        ax.set_yticks(range(len(labels)))
                        ax.set_yticklabels(labels)
                        ax.invert_yaxis()  # Top to bottom

                        # Add count labels
                        for j, count in enumerate(counts):
                            ax.text(count + max(counts) * 0.01, j, f"{count}", va="center", ha="left", fontsize=10)

                ax.set_ylabel("Count" if len(sorted_items) <= 5 else "")
                ax.grid(axis="y" if len(sorted_items) <= 5 else "x", alpha=0.3, linestyle="--")

            plt.suptitle(f"Feature Distribution: {feature_name}", fontsize=14, fontweight="bold", y=0.98)
            plt.tight_layout()
            plt.show()

            return feature_data

        except Exception as e:
            logger.error(f"Failed to create feature distribution plot: {e}")
            return feature_data

    def _plot_distribution_analysis(self, distribution_data: Dict) -> Dict:
        """Create distribution analysis visualization."""
        try:
            # Create subplot layout: coverage heatmap + distribution analysis
            fig, (ax1, ax2) = backend.create_figure(figsize=(15, 6), ncols=2)
            if fig is None:
                return distribution_data

            plt, sns = backend.setup_matplotlib()
            if plt is None:
                return distribution_data

            # Plot 1: Coverage Analysis Heatmap
            coverage_data = distribution_data["coverage_analysis"]
            split_names = list(coverage_data.keys())
            coverage_pcts = [coverage_data[name]["coverage_percentage"] for name in split_names]
            unique_counts = [coverage_data[name]["unique_count"] for name in split_names]

            # Create heatmap-style visualization
            colors = ["red" if pct < 50 else "orange" if pct < 80 else "green" for pct in coverage_pcts]

            bars1 = ax1.bar(split_names, coverage_pcts, color=colors, alpha=0.7, edgecolor="white", linewidth=2)
            ax1.set_title("Feature Coverage per Split", fontsize=12, fontweight="bold")
            ax1.set_ylabel("Coverage Percentage (%)")
            ax1.set_ylim(0, 100)
            ax1.grid(axis="y", alpha=0.3, linestyle="--")

            # Add percentage and count labels
            for bar, pct, count in zip(bars1, coverage_pcts, unique_counts):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width() / 2.0, height + 2, f"{pct:.1f}%\n({count} values)", ha="center", va="bottom", fontsize=10)

            # Plot 2: Missing Values Analysis
            missing_data = distribution_data["missing_values"]
            exclusive_data = distribution_data["exclusive_to_split"]

            # Prepare data for missing/exclusive analysis
            analysis_data = []
            for split_name in split_names:
                missing_count = len(missing_data.get(split_name, set()))
                exclusive_count = len(exclusive_data.get(split_name, set()))
                analysis_data.append([missing_count, exclusive_count])

            # Create stacked bar chart
            missing_counts = [d[0] for d in analysis_data]
            exclusive_counts = [d[1] for d in analysis_data]

            x_pos = range(len(split_names))
            ax2.bar(x_pos, missing_counts, label="Missing Values", color="salmon", alpha=0.8)
            ax2.bar(x_pos, exclusive_counts, bottom=missing_counts, label="Exclusive Values", color="lightblue", alpha=0.8)

            ax2.set_title("Distribution Issues Analysis", fontsize=12, fontweight="bold")
            ax2.set_xlabel("Split")
            ax2.set_ylabel("Number of Values")
            ax2.set_xticks(x_pos)
            ax2.set_xticklabels(split_names)
            ax2.legend()
            ax2.grid(axis="y", alpha=0.3, linestyle="--")

            # Add value labels
            for i, (missing, exclusive) in enumerate(zip(missing_counts, exclusive_counts)):
                if missing > 0:
                    ax2.text(i, missing / 2, str(missing), ha="center", va="center", fontweight="bold")
                if exclusive > 0:
                    ax2.text(i, missing + exclusive / 2, str(exclusive), ha="center", va="center", fontweight="bold")

            # Overall assessment
            has_issues = distribution_data["has_distribution_issues"]
            status_color = "orange" if has_issues else "green"
            status_text = "⚠️ DISTRIBUTION ISSUES DETECTED" if has_issues else "✅ BALANCED DISTRIBUTIONS"

            plt.suptitle(f"Feature Distribution Analysis - Status: {status_text}", fontsize=14, fontweight="bold", color=status_color, y=0.98)

            plt.tight_layout()
            plt.show()

            return distribution_data

        except Exception as e:
            logger.error(f"Failed to create distribution analysis plot: {e}")
            return distribution_data

    def _plot_characteristics(self, char_data: Dict) -> Dict:
        """Create characteristics visualization."""
        try:
            n_columns = len(char_data)
            if n_columns == 0:
                return char_data

            # Create dynamic subplot layout
            if n_columns == 1:
                fig, axes = backend.create_figure(figsize=(8, 6))
                axes = [axes]
            elif n_columns == 2:
                fig, axes = backend.create_figure(figsize=(12, 5), ncols=2)
            else:
                fig, axes = backend.create_figure(figsize=(15, 10), nrows=(n_columns + 1) // 2, ncols=2)
                axes = axes.flatten() if n_columns > 2 else axes

            if fig is None:
                return char_data

            plt, sns = backend.setup_matplotlib()
            if plt is None:
                return char_data

            for i, (column, split_data) in enumerate(char_data.items()):
                ax = axes[i]

                if column == "size":
                    self._plot_size_distribution(ax, split_data, plt, sns)
                elif column == "extension":
                    self._plot_extension_distribution(ax, split_data, plt, sns)
                elif column == "depth":
                    self._plot_depth_distribution(ax, split_data, plt, sns)
                else:
                    # Generic categorical or numerical plotting
                    self._plot_generic_characteristic(ax, column, split_data, plt, sns)

            # Hide unused subplots
            if n_columns > 2:
                for j in range(i + 1, len(axes)):
                    axes[j].set_visible(False)

            plt.suptitle("File Characteristics Analysis", fontsize=16, fontweight="bold", y=0.98)
            plt.tight_layout()
            plt.show()

            return char_data

        except Exception as e:
            logger.error(f"Failed to create characteristics plot: {e}")
            return char_data

    def _plot_size_distribution(self, ax, split_data, plt, sns):
        """Plot file size distributions across splits."""
        sizes_data = []
        labels = []

        for name, sizes in split_data.items():
            # Convert to MB for better readability
            sizes_mb = [s / (1024 * 1024) for s in sizes if isinstance(s, (int, float))]
            if sizes_mb:
                sizes_data.extend(sizes_mb)
                labels.extend([name] * len(sizes_mb))

        if sizes_data:
            # Create violin plot for size distribution
            import pandas as pd

            df = pd.DataFrame({"Size (MB)": sizes_data, "Split": labels})
            sns.violinplot(data=df, x="Split", y="Size (MB)", ax=ax)
            ax.set_title("File Size Distribution", fontweight="bold")
            ax.grid(axis="y", alpha=0.3, linestyle="--")
        else:
            ax.text(0.5, 0.5, "No size data available", ha="center", va="center", transform=ax.transAxes)
            ax.set_title("File Size Distribution", fontweight="bold")

    def _plot_extension_distribution(self, ax, split_data, plt, sns):
        """Plot file extension distributions across splits."""
        # Collect all extensions across splits
        all_extensions = set()
        for extensions in split_data.values():
            all_extensions.update(extensions)

        extension_counts = {ext: [] for ext in all_extensions}
        split_names = list(split_data.keys())

        for split_name, extensions in split_data.items():
            ext_count = {}
            for ext in extensions:
                ext_count[ext] = ext_count.get(ext, 0) + 1

            for ext in all_extensions:
                extension_counts[ext].append(ext_count.get(ext, 0))

        # Create stacked bar chart
        bottom = [0] * len(split_names)
        colors = sns.color_palette("husl", len(all_extensions))

        for i, (ext, counts) in enumerate(extension_counts.items()):
            ax.bar(split_names, counts, bottom=bottom, label=ext, color=colors[i], alpha=0.8)
            # Update bottom for stacking
            bottom = [b + c for b, c in zip(bottom, counts)]

        ax.set_title("File Extension Distribution", fontweight="bold")
        ax.set_ylabel("Count")
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        ax.grid(axis="y", alpha=0.3, linestyle="--")

    def _plot_depth_distribution(self, ax, split_data, plt, sns):
        """Plot directory depth distributions across splits."""
        depth_data = []
        labels = []

        for name, depths in split_data.items():
            valid_depths = [d for d in depths if isinstance(d, (int, float))]
            if valid_depths:
                depth_data.extend(valid_depths)
                labels.extend([name] * len(valid_depths))

        if depth_data:
            # Create box plot for depth distribution
            import pandas as pd

            df = pd.DataFrame({"Depth": depth_data, "Split": labels})
            sns.boxplot(data=df, x="Split", y="Depth", ax=ax)
            ax.set_title("Directory Depth Distribution", fontweight="bold")
            ax.set_ylabel("Directory Depth")
            ax.grid(axis="y", alpha=0.3, linestyle="--")
        else:
            ax.text(0.5, 0.5, "No depth data available", ha="center", va="center", transform=ax.transAxes)
            ax.set_title("Directory Depth Distribution", fontweight="bold")

    def _plot_generic_characteristic(self, ax, column, split_data, plt, sns):
        """Plot generic characteristic distribution."""
        split_names = list(split_data.keys())

        # Determine if data is numerical or categorical
        all_values = []
        for values in split_data.values():
            all_values.extend(values)

        # Check if values are numeric
        numeric_values = []
        for val in all_values:
            try:
                numeric_values.append(float(val))
            except (ValueError, TypeError):
                break

        if len(numeric_values) == len(all_values) and len(all_values) > 0:
            # Numerical data - use box plot
            data_for_plot = []
            labels_for_plot = []

            for name, values in split_data.items():
                numeric_vals = [float(v) for v in values if v is not None]
                data_for_plot.extend(numeric_vals)
                labels_for_plot.extend([name] * len(numeric_vals))

            if data_for_plot:
                import pandas as pd

                df = pd.DataFrame({column: data_for_plot, "Split": labels_for_plot})
                sns.boxplot(data=df, x="Split", y=column, ax=ax)
        else:
            # Categorical data - use bar plot
            unique_values = list(set(all_values))[:10]  # Limit to top 10
            value_counts = {val: [] for val in unique_values}

            for split_name, values in split_data.items():
                val_count = {}
                for val in values:
                    if val in unique_values:
                        val_count[val] = val_count.get(val, 0) + 1

                for val in unique_values:
                    value_counts[val].append(val_count.get(val, 0))

            # Stacked bar chart
            bottom = [0] * len(split_names)
            colors = sns.color_palette("husl", len(unique_values))

            for i, (val, counts) in enumerate(value_counts.items()):
                ax.bar(split_names, counts, bottom=bottom, label=str(val)[:20], color=colors[i], alpha=0.8)
                bottom = [b + c for b, c in zip(bottom, counts)]

            ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")

        ax.set_title(f"{column.title()} Distribution", fontweight="bold")
        ax.grid(axis="y", alpha=0.3, linestyle="--")

    def _print_feature_summary(self, feature_data: Dict) -> None:
        """Print text summary of feature distribution."""
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"Feature Distribution: {feature_data['feature']}")
        table.add_column("Split", style="cyan")
        table.add_column("Total Values", justify="right", style="green")
        table.add_column("Unique Values", justify="right", style="yellow")
        table.add_column("Coverage", justify="right", style="magenta")

        total_unique = len(feature_data["all_values"])
        for name, data in feature_data["splits"].items():
            coverage = len(data["unique_values"]) / total_unique * 100
            table.add_row(name, str(data["count"]), str(data["unique_count"]), f"{coverage:.1f}%")

        console.print(table)

    def _print_distribution_summary(self, distribution_data: Dict) -> None:
        """Print text summary of distribution analysis."""
        from rich.console import Console

        console = Console()

        if distribution_data["has_distribution_issues"]:
            console.print("[bold orange1]⚠️  Distribution Issues Detected![/bold orange1]")

            if distribution_data["missing_values"]:
                console.print("\n[yellow]Missing values per split:[/yellow]")
                for split, missing in distribution_data["missing_values"].items():
                    console.print(f"  {split}: {len(missing)} missing values")

            if distribution_data["exclusive_to_split"]:
                console.print("\n[yellow]Values exclusive to each split:[/yellow]")
                for split, exclusive in distribution_data["exclusive_to_split"].items():
                    console.print(f"  {split}: {len(exclusive)} exclusive values")
        else:
            console.print("[bold green]✓ Balanced feature distributions across splits[/bold green]")

    def _print_characteristics_summary(self, char_data: Dict) -> None:
        """Print text summary of characteristics analysis."""
        from rich.console import Console

        console = Console()
        console.print("[cyan]File Characteristics Summary[/cyan]")

        for column, split_data in char_data.items():
            console.print(f"\n[yellow]{column.title()}:[/yellow]")
            for split_name, values in split_data.items():
                if values:
                    unique_count = len(set(values))
                    console.print(f"  {split_name}: {len(values)} files, {unique_count} unique values")


def analyze_splits(
    splits: Tuple, split_names: Optional[List[str]] = None, feature: Optional[Union[str, List[str]]] = None, original_data: Optional[Any] = None
) -> SplitAnalyzer:
    """Create a SplitAnalyzer instance for analyzing ML data splits.

    This is the main entry point for split analysis functionality.

    Args:
        splits: Tuple of DataFrames from ml.split_data
        split_names: Optional names for the splits
        feature: Feature(s) used for splitting
        original_data: Original DataFrame before splitting

    Returns:
        SplitAnalyzer instance for further analysis

    """
    return SplitAnalyzer(splits, split_names, feature, original_data)
