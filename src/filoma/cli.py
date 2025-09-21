"""Interactive CLI for filoma using Typer and questionary."""

from pathlib import Path
from typing import Any, List, Optional

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import filoma

app = typer.Typer(
    name="filoma",
    help="Interactive filesystem profiling and analysis tool",
    rich_markup_mode="rich",
)
console = Console()


def show_welcome(current_dir: Path) -> None:
    """Display welcome message and current directory."""
    welcome_text = f"""
[bold blue]🗂️  Filoma Interactive CLI[/bold blue]

Current directory: [green]{current_dir}[/green]

Use arrow keys to navigate menus. Press Ctrl+C to exit anytime.
    """
    console.print(Panel(welcome_text, title="Welcome", border_style="blue"))


def get_directory_contents(path: Path) -> tuple[List[Path], List[Path]]:
    """Get directories and files in the given path."""
    try:
        items = list(path.iterdir())
        directories = [item for item in items if item.is_dir() and not item.name.startswith(".")]
        files = [item for item in items if item.is_file() and not item.name.startswith(".")]

        # Sort both lists
        directories.sort(key=lambda x: x.name.lower())
        files.sort(key=lambda x: x.name.lower())

        return directories, files
    except PermissionError:
        console.print(f"[red]Permission denied accessing {path}[/red]")
        return [], []


def create_file_browser_choices(current_dir: Path) -> List[questionary.Choice]:
    """Create choices for the file browser menu."""
    choices = []

    # Add parent directory option (unless we're at root)
    if current_dir.parent != current_dir:
        choices.append(questionary.Choice("📁 .. (Parent Directory)", value=("parent", current_dir.parent)))

    # Get directory contents
    directories, files = get_directory_contents(current_dir)

    # Add directories
    for directory in directories:
        choices.append(questionary.Choice(f"📁 {directory.name}/", value=("directory", directory)))

    # Add files
    for file in files:
        file_icon = get_file_icon(file)
        choices.append(questionary.Choice(f"{file_icon} {file.name}", value=("file", file)))

    # Add action options
    choices.append(questionary.Choice("━━━━━━━━━━━━━━━━━━━━━━━━", disabled=True))
    choices.append(questionary.Choice("🔍 Probe current directory", value=("probe_dir", current_dir)))
    choices.append(questionary.Choice("❌ Exit", value=("exit", None)))

    return choices


def get_file_icon(file_path: Path) -> str:
    """Get an appropriate icon for the file type."""
    suffix = file_path.suffix.lower()

    # Image files
    if suffix in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".zarr"]:
        return "🖼️"
    # Numpy files
    elif suffix == ".npy":
        return "🔢"
    # Data files
    elif suffix in [".csv", ".json", ".xml", ".yaml", ".yml"]:
        return "📊"
    # Code files
    elif suffix in [".py", ".rs", ".js", ".ts", ".html", ".css"]:
        return "💻"
    # Documents
    elif suffix in [".txt", ".md", ".pdf", ".doc", ".docx"]:
        return "📄"
    # Archive files
    elif suffix in [".zip", ".tar", ".gz", ".rar"]:
        return "📦"
    else:
        return "📄"


def show_probe_menu(item_path: Path, item_type: str) -> Optional[str]:
    """Show menu for probe actions."""
    if item_type == "file":
        choices = [
            questionary.Choice("🔍 Auto Probe (detect type)", value="probe"),
            questionary.Choice("📄 Probe as File", value="probe_file"),
            questionary.Choice("🖼️ Probe as Image", value="probe_image"),
            questionary.Choice("📊 Probe to DataFrame", value="probe_to_df"),
            questionary.Choice("🔙 Back", value="back"),
        ]
        title = f"How would you like to probe: {item_path.name}?"
    else:  # directory
        choices = [
            questionary.Choice("🔍 Auto Probe Directory", value="probe"),
            questionary.Choice("📊 Probe to DataFrame", value="probe_to_df"),
            questionary.Choice("🔙 Back", value="back"),
        ]
        title = f"How would you like to probe: {item_path.name}/?"

    return questionary.select(
        title,
        choices=choices,
        style=questionary.Style(
            [
                ("selected", "fg:#00aa00 bold"),
                ("pointer", "fg:#673ab7 bold"),
                ("question", "bold"),
            ]
        ),
    ).ask()


def execute_probe_with_spinner(probe_func, path: Path, **kwargs) -> Any:
    """Execute a probe function with a loading spinner."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Probing {path.name}...", total=None)
        try:
            result = probe_func(str(path), **kwargs)
            progress.update(task, description=f"✅ Completed probing {path.name}")
            return result
        except Exception as e:
            progress.update(task, description=f"❌ Failed to probe {path.name}")
            console.print(f"[red]Error: {e}[/red]")
            return None


def display_probe_result(result: Any, probe_type: str, path: Path) -> None:
    """Display the probe result in a nice format."""
    if result is None:
        return

    console.print(f"\n[bold green]✅ Probe Results for {path.name}[/bold green]")

    # Create a table for the results
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Property", style="dim")
    table.add_column("Value")

    if hasattr(result, "__dict__"):
        # For dataclass results
        for key, value in result.__dict__.items():
            if value is not None:
                # Format large numbers nicely
                if isinstance(value, int) and value > 1024:
                    if value > 1024**3:
                        formatted = f"{value / (1024**3):.2f} GB"
                    elif value > 1024**2:
                        formatted = f"{value / (1024**2):.2f} MB"
                    elif value > 1024:
                        formatted = f"{value / 1024:.2f} KB"
                    else:
                        formatted = str(value)
                    table.add_row(key.replace("_", " ").title(), formatted)
                else:
                    table.add_row(key.replace("_", " ").title(), str(value))

    console.print(table)

    # If it's a DataFrame result, show some info about it
    if hasattr(result, "df") and probe_type == "probe_to_df":
        console.print("\n[bold blue]📊 DataFrame Info:[/bold blue]")
        try:
            df = result.df
            console.print(f"Shape: {df.shape}")
            console.print(f"Columns: {list(df.columns)}")
        except Exception as e:
            console.print(f"[yellow]Could not display DataFrame info: {e}[/yellow]")


def browse_and_probe(start_dir: Path) -> None:
    """Browse files and directories interactively with probe capabilities."""
    current_dir = start_dir

    while True:
        console.clear()
        show_welcome(current_dir)

        # Create choices for current directory
        choices = create_file_browser_choices(current_dir)

        # Show the selection menu
        selection = questionary.select(
            f"Select an item in {current_dir}:",
            choices=choices,
            style=questionary.Style(
                [
                    ("selected", "fg:#00aa00 bold"),
                    ("pointer", "fg:#673ab7 bold"),
                    ("question", "bold"),
                ]
            ),
        ).ask()

        if selection is None:  # User pressed Ctrl+C
            break

        action_type, item_path = selection

        if action_type == "exit":
            break
        elif action_type == "parent":
            current_dir = item_path
        elif action_type == "directory":
            # Ask if they want to enter the directory or probe it
            choice = questionary.select(
                f"What would you like to do with {item_path.name}/?",
                choices=[
                    questionary.Choice("📁 Enter directory", value="enter"),
                    questionary.Choice("🔍 Probe directory", value="probe"),
                    questionary.Choice("🔙 Back", value="back"),
                ],
                style=questionary.Style(
                    [
                        ("selected", "fg:#00aa00 bold"),
                        ("pointer", "fg:#673ab7 bold"),
                    ]
                ),
            ).ask()

            if choice == "enter":
                current_dir = item_path
            elif choice == "probe":
                probe_action = show_probe_menu(item_path, "directory")
                if probe_action and probe_action != "back":
                    execute_probe_action(probe_action, item_path)
        elif action_type == "file":
            probe_action = show_probe_menu(item_path, "file")
            if probe_action and probe_action != "back":
                execute_probe_action(probe_action, item_path)
        elif action_type == "probe_dir":
            probe_action = show_probe_menu(item_path, "directory")
            if probe_action and probe_action != "back":
                execute_probe_action(probe_action, item_path)


def process_dataframe_interactively(df_result: Any, path: Path) -> None:
    """Interactive DataFrame processing and analysis."""
    while True:
        try:
            df = df_result.df  # Get the underlying Polars DataFrame

            console.print(f"\n[bold blue]📊 DataFrame Analysis for {path.name}[/bold blue]")
            console.print(f"Shape: [green]{df.shape}[/green]")

            # Create menu options
            choices = [
                questionary.Choice("📊 Show DataFrame Info", value="info"),
                questionary.Choice("👀 Show Head (first 10 rows)", value="head"),
                questionary.Choice("👀 Show Head (custom rows)", value="head_custom"),
                questionary.Choice("📋 Show Columns", value="columns"),
                questionary.Choice("📈 Column Analysis", value="column_analysis"),
                questionary.Choice("🔍 Basic Statistics", value="describe"),
                questionary.Choice("🔎 Search/Filter", value="filter"),
                questionary.Choice("🤖 Split for ML", value="ml_split"),
                questionary.Choice("💾 Export Options", value="export"),
                questionary.Choice("🔙 Back to File Browser", value="back"),
            ]

            choice = questionary.select(
                "What would you like to do with this DataFrame?",
                choices=choices,
                style=questionary.Style(
                    [
                        ("selected", "fg:#00aa00 bold"),
                        ("pointer", "fg:#673ab7 bold"),
                        ("question", "bold"),
                    ]
                ),
            ).ask()

            if choice is None or choice == "back":
                break
            elif choice == "info":
                show_dataframe_info(df)
            elif choice == "head":
                show_dataframe_head(df, 10)
            elif choice == "head_custom":
                rows = questionary.text("How many rows to show?", default="10").ask()
                try:
                    n_rows = int(rows) if rows else 10
                    show_dataframe_head(df, n_rows)
                except ValueError:
                    console.print("[red]Invalid number, showing 10 rows[/red]")
                    show_dataframe_head(df, 10)
            elif choice == "columns":
                show_dataframe_columns(df)
            elif choice == "column_analysis":
                analyze_column_interactively(df)
            elif choice == "describe":
                show_dataframe_describe(df)
            elif choice == "filter":
                filter_dataframe_interactively(df)
            elif choice == "ml_split":
                split_dataframe_for_ml(df_result, path)
            elif choice == "export":
                export_dataframe_interactively(df, path)

            # Wait for user input before showing menu again
            console.print("\n[dim]Press Enter to continue...[/dim]")
            input()

        except Exception as e:
            console.print(f"[red]Error processing DataFrame: {e}[/red]")
            console.print("\n[dim]Press Enter to continue...[/dim]")
            input()
            break


def show_dataframe_info(df: Any) -> None:
    """Display DataFrame information."""
    console.print("\n[bold blue]📊 DataFrame Information[/bold blue]")

    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Property", style="dim")
    table.add_column("Value")

    # Basic info
    table.add_row("Shape", f"{df.shape[0]} rows × {df.shape[1]} columns")
    table.add_row("Columns", str(len(df.columns)))

    # Column types
    try:
        dtypes = df.dtypes
        type_counts = {}
        for dtype in dtypes:
            dtype_str = str(dtype)
            type_counts[dtype_str] = type_counts.get(dtype_str, 0) + 1

        type_summary = ", ".join([f"{count} {dtype}" for dtype, count in type_counts.items()])
        table.add_row("Column Types", type_summary)
    except Exception:
        table.add_row("Column Types", "Unable to determine")

    # Memory usage estimation
    try:
        memory_mb = df.estimated_size("mb")
        table.add_row("Estimated Memory", f"{memory_mb:.2f} MB")
    except Exception:
        table.add_row("Estimated Memory", "Unable to determine")

    console.print(table)


def show_dataframe_head(df: Any, n_rows: int = 10) -> None:
    """Display the first n rows of the DataFrame."""
    console.print(f"\n[bold blue]👀 First {n_rows} rows[/bold blue]")

    try:
        head_df = df.head(n_rows)

        # Convert to pandas for nicer display if possible
        try:
            pandas_df = head_df.to_pandas()
            console.print(pandas_df.to_string(max_cols=10, max_colwidth=50))
        except Exception:
            # Fallback to basic display
            console.print(str(head_df))
    except Exception as e:
        console.print(f"[red]Error displaying head: {e}[/red]")


def show_dataframe_columns(df: Any) -> None:
    """Display DataFrame columns with types."""
    console.print("\n[bold blue]📋 DataFrame Columns[/bold blue]")

    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Column", style="dim")
    table.add_column("Type")
    table.add_column("Sample Values")

    try:
        columns = df.columns
        dtypes = df.dtypes

        for i, (col, dtype) in enumerate(zip(columns, dtypes)):
            # Get sample values
            try:
                sample_vals = df.select(col).head(3).to_series().to_list()
                sample_str = ", ".join([str(val)[:30] for val in sample_vals if val is not None])
                if len(sample_str) > 60:
                    sample_str = sample_str[:60] + "..."
            except Exception:
                sample_str = "Unable to sample"

            table.add_row(col, str(dtype), sample_str)

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error displaying columns: {e}[/red]")


def show_dataframe_describe(df: Any) -> None:
    """Show basic statistics for numeric columns."""
    console.print("\n[bold blue]📈 Basic Statistics[/bold blue]")

    try:
        # Try to get numeric columns and describe them
        numeric_df = df.select([col for col in df.columns if df[col].dtype in [df.dtypes[0].__class__().__name__ for dtype in [int, float]]])

        if numeric_df.width > 0:
            desc = numeric_df.describe()

            # Convert to pandas for nicer display
            try:
                pandas_desc = desc.to_pandas()
                console.print(pandas_desc.to_string())
            except Exception:
                console.print(str(desc))
        else:
            console.print("[yellow]No numeric columns found for statistical analysis[/yellow]")
    except Exception as e:
        console.print(f"[red]Error generating statistics: {e}[/red]")


def analyze_column_interactively(df: Any) -> None:
    """Interactive column analysis."""
    try:
        columns = df.columns

        # Let user select a column
        choices = [questionary.Choice(col, value=col) for col in columns]
        choices.append(questionary.Choice("🔙 Back", value="back"))

        selected_col = questionary.select(
            "Select a column to analyze:",
            choices=choices,
            style=questionary.Style(
                [
                    ("selected", "fg:#00aa00 bold"),
                    ("pointer", "fg:#673ab7 bold"),
                ]
            ),
        ).ask()

        if selected_col == "back" or selected_col is None:
            return

        # Analysis options for the selected column
        analysis_choices = [
            questionary.Choice("📊 Value Counts", value="value_counts"),
            questionary.Choice("🔢 Unique Values", value="unique"),
            questionary.Choice("📈 Basic Stats", value="stats"),
            questionary.Choice("❓ Null Count", value="nulls"),
            questionary.Choice("🔙 Back", value="back"),
        ]

        analysis_choice = questionary.select(
            f"What analysis for column '{selected_col}'?",
            choices=analysis_choices,
            style=questionary.Style(
                [
                    ("selected", "fg:#00aa00 bold"),
                    ("pointer", "fg:#673ab7 bold"),
                ]
            ),
        ).ask()

        if analysis_choice == "back" or analysis_choice is None:
            return

        console.print(f"\n[bold blue]📊 Analysis for column: {selected_col}[/bold blue]")

        if analysis_choice == "value_counts":
            try:
                value_counts = df[selected_col].value_counts()
                console.print(f"\n[green]Value counts for '{selected_col}':[/green]")

                # Convert to pandas for display
                try:
                    pandas_vc = value_counts.to_pandas()
                    console.print(pandas_vc.to_string())
                except Exception:
                    console.print(str(value_counts))
            except Exception as e:
                console.print(f"[red]Error computing value counts: {e}[/red]")

        elif analysis_choice == "unique":
            try:
                unique_vals = df[selected_col].unique()
                console.print(f"\n[green]Unique values in '{selected_col}' (first 20):[/green]")
                unique_list = unique_vals.to_list()[:20]
                for val in unique_list:
                    console.print(f"  • {val}")
                if len(unique_vals) > 20:
                    console.print(f"  ... and {len(unique_vals) - 20} more")
                console.print(f"\nTotal unique values: [bold]{len(unique_vals)}[/bold]")
            except Exception as e:
                console.print(f"[red]Error getting unique values: {e}[/red]")

        elif analysis_choice == "stats":
            try:
                table = Table(show_header=True, header_style="bold blue")
                table.add_column("Statistic")
                table.add_column("Value")

                # Basic stats
                table.add_row("Count", str(len(df)))

                try:
                    table.add_row("Unique", str(df[selected_col].n_unique()))
                except Exception:
                    pass

                try:
                    null_count = df[selected_col].null_count()
                    table.add_row("Null Count", str(null_count))
                    table.add_row("Non-null Count", str(len(df) - null_count))
                except Exception:
                    pass

                # For numeric columns, add more stats
                try:
                    if df[selected_col].dtype in ["Int64", "Float64", "Int32", "Float32"]:
                        table.add_row("Mean", f"{df[selected_col].mean():.4f}")
                        table.add_row("Std", f"{df[selected_col].std():.4f}")
                        table.add_row("Min", str(df[selected_col].min()))
                        table.add_row("Max", str(df[selected_col].max()))
                except Exception:
                    pass

                console.print(table)
            except Exception as e:
                console.print(f"[red]Error computing statistics: {e}[/red]")

        elif analysis_choice == "nulls":
            try:
                null_count = df[selected_col].null_count()
                total_count = len(df)
                null_pct = (null_count / total_count) * 100 if total_count > 0 else 0

                table = Table(show_header=True, header_style="bold blue")
                table.add_column("Metric")
                table.add_column("Value")

                table.add_row("Null Count", str(null_count))
                table.add_row("Non-null Count", str(total_count - null_count))
                table.add_row("Null Percentage", f"{null_pct:.2f}%")

                console.print(table)
            except Exception as e:
                console.print(f"[red]Error analyzing nulls: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error in column analysis: {e}[/red]")


def filter_dataframe_interactively(df: Any) -> None:
    """Interactive DataFrame filtering."""
    console.print("\n[bold blue]🔍 DataFrame Filtering[/bold blue]")
    console.print("[yellow]Note: This is a preview feature. Advanced filtering coming soon![/yellow]")

    try:
        # Simple column filtering
        column = questionary.select(
            "Select column to filter by:",
            choices=[questionary.Choice(col, value=col) for col in df.columns] + [questionary.Choice("🔙 Back", value="back")],
            style=questionary.Style(
                [
                    ("selected", "fg:#00aa00 bold"),
                    ("pointer", "fg:#673ab7 bold"),
                ]
            ),
        ).ask()

        if column == "back" or column is None:
            return

        # Show sample values
        console.print(f"\n[green]Sample values in '{column}':[/green]")
        try:
            sample_vals = df[column].head(10).to_list()
            for val in sample_vals:
                console.print(f"  • {val}")
        except Exception:
            console.print("Unable to show sample values")

        filter_value = questionary.text(f"Enter value to filter '{column}' by (case-sensitive):", default="").ask()

        if filter_value:
            try:
                filtered_df = df.filter(df[column] == filter_value)
                console.print(f"\n[green]Filtered DataFrame (rows where {column} = '{filter_value}'):[/green]")
                console.print(f"Filtered shape: [bold]{filtered_df.shape}[/bold]")

                if filtered_df.height > 0:
                    show_dataframe_head(filtered_df, min(10, filtered_df.height))
                else:
                    console.print("[yellow]No rows match the filter criteria[/yellow]")
            except Exception as e:
                console.print(f"[red]Error filtering DataFrame: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error in filtering: {e}[/red]")


def export_dataframe_interactively(df: Any, original_path: Path) -> None:
    """Interactive DataFrame export options."""
    console.print("\n[bold blue]💾 Export DataFrame[/bold blue]")

    export_choices = [
        questionary.Choice("📄 Export to CSV", value="csv"),
        questionary.Choice("📊 Export to JSON", value="json"),
        questionary.Choice("📋 Export to Parquet", value="parquet"),
        questionary.Choice("🔙 Back", value="back"),
    ]

    choice = questionary.select(
        "Choose export format:",
        choices=export_choices,
        style=questionary.Style(
            [
                ("selected", "fg:#00aa00 bold"),
                ("pointer", "fg:#673ab7 bold"),
            ]
        ),
    ).ask()

    if choice == "back" or choice is None:
        return

    # Suggest filename based on original path
    suggested_name = f"{original_path.stem}_analysis.{choice}"

    filename = questionary.text("Enter filename:", default=suggested_name).ask()

    if filename:
        try:
            output_path = Path(filename)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"Exporting to {choice.upper()}...", total=None)

                if choice == "csv":
                    df.write_csv(output_path)
                elif choice == "json":
                    df.write_json(output_path)
                elif choice == "parquet":
                    df.write_parquet(output_path)

                progress.update(task, description=f"✅ Exported to {output_path}")

            console.print(f"[green]✅ Successfully exported to: {output_path}[/green]")

        except Exception as e:
            console.print(f"[red]Export failed: {e}[/red]")


def split_dataframe_for_ml(df_result: Any, original_path: Path) -> None:
    """Interactive ML data splitting wizard."""
    console.print("\n[bold blue]🤖 ML Data Splitting[/bold blue]")

    try:
        df = df_result.df if hasattr(df_result, "df") else df_result

        # Check if we have path column
        path_col = None
        potential_path_cols = [col for col in df.columns if "path" in col.lower() or "file" in col.lower()]

        if not potential_path_cols:
            console.print("[red]❌ No path column found in DataFrame. ML splitting requires file paths.[/red]")
            return

        if len(potential_path_cols) == 1:
            path_col = potential_path_cols[0]
            console.print(f"[green]✅ Using path column: {path_col}[/green]")
        else:
            path_col = questionary.select(
                "Select the path column:",
                choices=[questionary.Choice(col, value=col) for col in potential_path_cols],
                style=questionary.Style(
                    [
                        ("selected", "fg:#00aa00 bold"),
                        ("pointer", "fg:#673ab7 bold"),
                    ]
                ),
            ).ask()

        if not path_col:
            return

        # Ask for split type
        split_type = questionary.select(
            "Choose splitting method:",
            choices=[
                questionary.Choice("📊 Ratio-based split (e.g., 70/20/10)", value="ratio"),
                questionary.Choice("📁 Existing folder structure (e.g., training/validation/testing)", value="mapping"),
                questionary.Choice("🔙 Back", value="back"),
            ],
            style=questionary.Style(
                [
                    ("selected", "fg:#00aa00 bold"),
                    ("pointer", "fg:#673ab7 bold"),
                ]
            ),
        ).ask()

        if split_type == "back" or split_type is None:
            return

        if split_type == "ratio":
            # Ratio-based splitting
            train_ratio = questionary.text(
                "Training ratio (0.0-1.0):", default="0.7", validate=lambda x: x.replace(".", "").isdigit() and 0 < float(x) < 1
            ).ask()

            val_ratio = questionary.text(
                "Validation ratio (0.0-1.0):", default="0.2", validate=lambda x: x.replace(".", "").isdigit() and 0 < float(x) < 1
            ).ask()

            if not train_ratio or not val_ratio:
                return

            train_ratio = float(train_ratio)
            val_ratio = float(val_ratio)
            test_ratio = 1.0 - train_ratio - val_ratio

            if test_ratio < 0:
                console.print("[red]❌ Invalid ratios: train + validation must be ≤ 1.0[/red]")
                return

            console.print(f"[cyan]Split ratios: Train={train_ratio:.1%}, Val={val_ratio:.1%}, Test={test_ratio:.1%}[/cyan]")

        elif split_type == "mapping":
            # Get unique folder patterns from paths - look for ML split folders
            folders = set()
            ml_folder_depth = None  # Track which depth contains ML folders

            # Filter to files only and get sample paths
            files_df = df.filter(df["is_file"]) if "is_file" in df.columns else df
            # Use strategic sampling to ensure we capture all split folders
            total_files = len(files_df)
            if total_files > 10000:
                # Sample from beginning, middle, and end to capture all folders
                sample_paths = []
                # First 3000 files
                sample_paths.extend(files_df.select(path_col).limit(3000).to_series().to_list())
                # Middle 4000 files
                middle_start = total_files // 2 - 2000
                sample_paths.extend(files_df.select(path_col).slice(middle_start, 4000).to_series().to_list())
                # Last 3000 files
                sample_paths.extend(files_df.select(path_col).tail(3000).to_series().to_list())
            else:
                sample_paths = files_df.select(path_col).to_series().to_list()

            for path in sample_paths:
                try:
                    path_obj = Path(path)
                    # Look at multiple levels to find ML split folders
                    # Check immediate parent and grandparent for common ML folder names
                    common_ml_folders = {"train", "training", "val", "valid", "validation", "test", "testing"}

                    # Check immediate parent
                    if path_obj.parent.name.lower() in common_ml_folders:
                        folders.add(path_obj.parent.name)
                        if ml_folder_depth is None:
                            ml_folder_depth = -2  # Parent is at -2 position
                    # Check grandparent (for nested structures like train/class_name/file.jpg)
                    elif path_obj.parent.parent.name.lower() in common_ml_folders:
                        folders.add(path_obj.parent.parent.name)
                        if ml_folder_depth is None:
                            ml_folder_depth = -3  # Grandparent is at -3 position
                    # If no ML folders found, collect immediate parents for manual mapping
                    else:
                        if path_obj.parent.name:
                            folders.add(path_obj.parent.name)
                            if ml_folder_depth is None:
                                ml_folder_depth = -2  # Default to parent

                except Exception:
                    continue

            if not folders:
                console.print("[red]❌ No folder structure detected in paths[/red]")
                return

            # Default to -2 if we couldn't determine the depth
            if ml_folder_depth is None:
                ml_folder_depth = -2

            folders = sorted(list(folders))
            console.print(f"[cyan]Found folders: {', '.join(folders)}[/cyan]")

            # Interactive mapping
            split_mapping = {}
            console.print("\n[bold blue]📂 Folder Mapping Instructions:[/bold blue]")
            console.print("[yellow]Use SPACE to select/deselect folders, ENTER to confirm selection[/yellow]")
            console.print("[yellow]You can map the same folder to multiple splits if needed[/yellow]")

            # Check for obvious mappings and suggest them
            obvious_mappings = {}
            split_names = ["train", "val", "test"]

            for split_name in split_names:
                for folder in folders:
                    folder_lower = folder.lower()
                    if (
                        (split_name == "train" and folder_lower in ["train", "training"])
                        or (split_name == "val" and folder_lower in ["val", "valid", "validation"])
                        or (split_name == "test" and folder_lower in ["test", "testing"])
                    ):
                        obvious_mappings[split_name] = [folder]
                        break

            if obvious_mappings:
                console.print(f"\n[bold green]🎯 Suggested mapping based on folder names:[/bold green]")
                for split_name, folder_list in obvious_mappings.items():
                    console.print(f"  {split_name.upper()}: {', '.join(folder_list)}")

                use_suggested = questionary.confirm("Use suggested mapping?").ask()
                if use_suggested:
                    split_mapping = obvious_mappings
                    console.print("[green]✅ Using suggested mapping[/green]")
                else:
                    console.print("[yellow]⚙ Manual mapping...[/yellow]")

            # Manual mapping if no suggestions used
            if not split_mapping:
                for split_name in ["train", "val", "test"]:
                    console.print(f"\n[bold]Map folders for {split_name.upper()} split:[/bold]")
                    console.print(f"[dim]Available folders: {', '.join(folders)}[/dim]")

                    while True:  # Loop until user makes a selection or skips
                        selected_folders = questionary.checkbox(
                            f"Select folders for {split_name} (SPACE to select, ENTER to confirm):",
                            choices=[questionary.Choice(folder, value=folder) for folder in folders],
                            style=questionary.Style(
                                [
                                    ("selected", "fg:#00aa00 bold"),
                                    ("pointer", "fg:#673ab7 bold"),
                                ]
                            ),
                        ).ask()

                        if selected_folders:
                            split_mapping[split_name] = selected_folders
                            console.print(f"[green]✓ Mapped {split_name}: {', '.join(selected_folders)}[/green]")
                            break
                        else:
                            skip = questionary.confirm(f"Skip {split_name} split (no folders selected)?").ask()
                            if skip:
                                console.print(f"[yellow]⚠ Skipped {split_name} split[/yellow]")
                                break
                            # If not skipping, loop again to retry selection

            if not split_mapping:
                console.print("[red]❌ No folder mapping provided - all splits were skipped[/red]")
                return

            console.print(f"\n[bold green]✅ Final mapping:[/bold green] {split_mapping}")

        # Ask about files-only filtering
        files_only = True  # Default to files only for ML
        if "is_file" in df.columns:
            files_count = len(df.filter(df["is_file"]))
            total_count = len(df)
            dirs_count = total_count - files_count

            if dirs_count > 0:
                console.print(f"[cyan]Dataset contains {files_count:,} files and {dirs_count:,} directories[/cyan]")
                files_only = questionary.confirm("Include only files in the split (recommended for ML)?", default=True).ask()

        # Confirm and execute split
        proceed = questionary.confirm("Proceed with ML data splitting?").ask()

        if not proceed:
            return

        # Import and execute split
        from filoma.ml import split_data

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Splitting data for ML...", total=None)

            if split_type == "ratio":
                result = split_data(df, train_ratio=train_ratio, val_ratio=val_ratio, path_col=path_col, files_only=files_only)
                feature_mapping = None
            else:  # mapping
                # Transform split-to-folders mapping into feature-to-split mapping
                # CLI format: {'train': ['train'], 'val': ['valid'], 'test': ['test']}
                # ML format: {'train': 'train', 'valid': 'val', 'test': 'test'}
                feature_mapping = {}
                for split_name, folder_list in split_mapping.items():
                    for folder in folder_list:
                        feature_mapping[folder] = split_name

                result = split_data(
                    df,
                    split_mapping=feature_mapping,
                    path_col=path_col,
                    files_only=files_only,
                    path_parts=(ml_folder_depth,),  # Use the dynamically determined depth
                )

            progress.update(task, description="✅ Data split complete!")

        # Display results
        console.print("\n[bold green]🎉 ML Split Results:[/bold green]")

        # Unpack the tuple result
        train_df, val_df, test_df = result

        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Split")
        table.add_column("Count")
        table.add_column("Percentage")

        total_count = len(train_df) + len(val_df) + len(test_df)

        if total_count == 0:
            console.print("[red]❌ Split resulted in empty datasets. Check your folder mapping and path structure.[/red]")
            if feature_mapping:
                console.print(f"[yellow]Debug info: Expected folders {list(feature_mapping.keys())} in your path structure[/yellow]")
            return

        table.add_row("Train", str(len(train_df)), f"{len(train_df) / total_count:.1%}")
        table.add_row("Validation", str(len(val_df)), f"{len(val_df) / total_count:.1%}")
        table.add_row("Test", str(len(test_df)), f"{len(test_df) / total_count:.1%}")
        table.add_row("Total", str(total_count), "100.0%")

        console.print(table)

        # Ask about exporting
        export_choice = questionary.confirm("Export split datasets to separate files?").ask()

        if export_choice:
            base_name = questionary.text("Base filename (without extension):", default=f"{original_path.stem}_ml_split").ask()

            if base_name:
                try:
                    train_df.write_csv(f"{base_name}_train.csv")
                    val_df.write_csv(f"{base_name}_val.csv")
                    test_df.write_csv(f"{base_name}_test.csv")

                    console.print(f"[green]✅ Exported train/val/test datasets with prefix: {base_name}[/green]")
                except Exception as e:
                    console.print(f"[red]Export failed: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error in ML splitting: {e}[/red]")


def execute_probe_action(action: str, path: Path) -> None:
    """Execute the selected probe action."""
    try:
        if action == "probe":
            result = execute_probe_with_spinner(filoma.probe, path)
            display_probe_result(result, action, path)
        elif action == "probe_file":
            result = execute_probe_with_spinner(filoma.probe_file, path)
            display_probe_result(result, action, path)
        elif action == "probe_image":
            result = execute_probe_with_spinner(filoma.probe_image, path)
            display_probe_result(result, action, path)
        elif action == "probe_to_df":
            result = execute_probe_with_spinner(filoma.probe_to_df, path)
            display_probe_result(result, action, path)

            # If it's a DataFrame result, offer DataFrame processing options
            if result and hasattr(result, "df"):
                process_dataframe_interactively(result, path)
                return

        # Wait for user to press enter before continuing
        console.print("\n[dim]Press Enter to continue...[/dim]")
        input()

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        console.print("\n[dim]Press Enter to continue...[/dim]")
        input()


@app.command()
def main(path: Optional[str] = typer.Argument(None, help="Starting directory (defaults to current directory)")) -> None:
    """Interactive filesystem profiling and analysis tool.

    Navigate directories with arrow keys and probe files/folders using filoma's analysis functions.
    """
    try:
        # Determine starting directory
        if path is not None:
            start_dir = Path(path).resolve()
            if not start_dir.exists():
                console.print(f"[red]Error: Directory '{path}' does not exist[/red]")
                raise typer.Exit(1)
            if not start_dir.is_dir():
                console.print(f"[red]Error: '{path}' is not a directory[/red]")
                raise typer.Exit(1)
        else:
            start_dir = Path.cwd()

        # Start the interactive browser
        browse_and_probe(start_dir)

    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye! 👋[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()


def cli() -> None:
    """Entry point for the filoma CLI."""
    app()
