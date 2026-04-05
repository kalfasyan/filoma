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
from filoma._version import __version__

app = typer.Typer(
    name="filoma",
    help="Interactive filesystem profiling and analysis tool",
    rich_markup_mode="rich",
    add_completion=False,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"filoma {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(False, "--version", help="Show version information", callback=version_callback),
) -> None:
    """Filoma - Interactive filesystem profiling and analysis tool."""
    return
brain_app = typer.Typer(
    name="brain",
    help="Intelligent filesystem analysis using AI",
    rich_markup_mode="rich",
)
app.add_typer(brain_app)

mcp_app = typer.Typer(
    name="mcp",
    help="MCP server for external agent integration",
    rich_markup_mode="rich",
)
app.add_typer(mcp_app)

console = Console()


@brain_app.command("chat")
def brain_chat(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="AI model to use"),
) -> None:
    """Start an interactive chat session with the Filoma Brain."""
    from filoma.brain.cli import chat as start_chat

    start_chat(model=model)


@mcp_app.command("serve")
def mcp_serve() -> None:
    r"""Start the MCP server for external agent integration.

    This command starts a Model Context Protocol (MCP) server that exposes
    filoma's filesystem analysis tools to any MCP-compatible client.

    The server runs on stdio transport by default, making it compatible with
    Claude Desktop, Cline, and other MCP clients.

    Example:\n
        filoma mcp serve\n
    Environment variables:\n
        FILOMA_MCP_TRANSPORT: 'stdio' (default) or 'sse'\n
        FILOMA_MCP_PORT: Port for SSE transport (default: 8000)
    """
    import asyncio

    from filoma.mcp_server import main

    console.print("[bold blue]🔌 Starting Filoma MCP Server...[/bold blue]")
    console.print("[dim]Server will run until interrupted (Ctrl+C)[/dim]\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]MCP server stopped.[/yellow]")


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


@app.command()
def verify(
    reference: str = typer.Argument(..., help="Path to reference snapshot or manifest file"),
    target: str = typer.Option(..., "--target", "-t", help="Target directory for integrity check"),
) -> None:
    """Verify dataset integrity using snapshots or manifests."""
    from filoma.core.verifier import verify_dataset

    console.print(f"[bold blue]Checking integrity of {target} against {reference}...[/bold blue]")
    try:
        results = verify_dataset(reference, target_path=target)
        console.print("[green]✅ Integrity check complete.[/green]")
        console.print(results)
    except Exception as e:
        console.print(f"[red]Error during verification: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def quality(
    path: str = typer.Argument(..., help="Dataset path for quality check"),
) -> None:
    """Run data quality analysis on a dataset."""
    from filoma.core.verifier import DatasetVerifier

    console.print(f"[bold blue]Running quality checks on {path}...[/bold blue]")
    try:
        verifier = DatasetVerifier(path)
        verifier.run_all()
        verifier.print_summary()
    except Exception as e:
        console.print(f"[red]Error during quality checks: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def dedup(
    paths: List[str] = typer.Argument(..., help="Path(s) to check for duplicates"),
    cross_dir: bool = typer.Option(False, "--cross-dir", help="Only check for duplicates across provided paths"),
) -> None:
    """Find and report duplicate files in one or more directories."""
    import filoma

    console.print(f"[bold blue]Checking for duplicates in {', '.join(paths)}...[/bold blue]")
    try:
        # Create a single dataframe from all paths if cross-dir checking,
        # or process them individually. For simplicity, we merge.
        # Actually, probe_to_df usually takes a single path.
        # We can create a consolidated DataFrame.
        combined_dfs = [filoma.probe_to_df(p) for p in paths]
        combined_df = combined_dfs[0]
        for df in combined_dfs[1:]:
            combined_df = combined_df.vstack(df.to_polars())

        # Wrapped as a filoma.DataFrame
        df = filoma.DataFrame(combined_df)

        # If cross_dir, restrict duplicate search to span different directories
        cross_dir_paths = paths if cross_dir else None

        dupes = df.evaluate_duplicates(show_table=True, cross_dir_paths=cross_dir_paths)

        for category in ["exact", "text", "image"]:
            groups = dupes.get(category, [])
            if groups:
                console.print(f"\n[bold yellow]{category.capitalize()} duplicates ({len(groups)} groups):[/bold yellow]")
                for i, group in enumerate(groups):
                    console.print(f"Group {i + 1}:")
                    for file_path in group:
                        console.print(f"  • {file_path}")
            else:
                console.print(f"\n[dim]No {category} duplicates found.[/dim]")
    except Exception as e:
        console.print(f"[red]Error during duplicate check: {e}[/red]")
        raise typer.Exit(1)


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
    choices.append(questionary.Choice("━━━━━━━━━━━━━━━━━━━━━━━━", disabled=""))
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
                    if df[selected_col].dtype in [
                        "Int64",
                        "Float64",
                        "Int32",
                        "Float32",
                    ]:
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


def cli() -> None:
    """Entry point for the filoma CLI."""
    app()


if __name__ == "__main__":
    app()
