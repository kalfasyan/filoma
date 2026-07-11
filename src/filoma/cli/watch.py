""":command:`filoma watch` — Dataset drift detection and gate checking.

Snapshots a directory, compares against a previous snapshot (if any),
checks quality gates, and exports the diff report as JSON.
"""

import json
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from ._app import app


@app.command("watch")
def watch_cmd(
    path: str = typer.Argument(".", help="Directory path to watch"),
    snapshot: Optional[Path] = typer.Option(None, "--snapshot", "-s", help="Compare against this snapshot JSON file"),
    gates: Optional[Path] = typer.Option(None, "--gates", "-g", help="Quality gates YAML file"),
    mode: str = typer.Option("fast", "--mode", "-m", help="Snapshot mode: fast or deep"),
    export: Optional[Path] = typer.Option(None, "--export", "-o", help="Write JSON diff report to this path"),
) -> None:
    """Watch a directory for dataset drift.

    Creates a snapshot of the current state, optionally compares it
    against a previous snapshot, checks quality gate thresholds, and
    prints a human-readable summary.

    Examples:
        filoma watch ./data

        filoma watch ./data --snapshot baseline.json --gates gates.yml

        filoma watch ./data --mode deep --export report.json

    """
    from filoma.core.gates import check_gates
    from filoma.core.snapshot import DatasetSnapshot, verify
    from filoma.core.snapshot import snapshot as create_snapshot

    console = Console()
    p = Path(path).expanduser().resolve()

    if not p.exists():
        console.print(f"[red]Error:[/red] Path '{p}' does not exist.")
        raise typer.Exit(code=1)
    if not p.is_dir():
        console.print(f"[red]Error:[/red] '{p}' is not a directory.")
        raise typer.Exit(code=1)

    valid_modes = {"fast", "deep"}
    if mode not in valid_modes:
        console.print(f"[red]Error:[/red] Mode must be one of {sorted(valid_modes)}, got '{mode}'.")
        raise typer.Exit(code=1)

    snap_mode = mode

    # 1. Load or create snapshot
    if snapshot and snapshot.exists():
        console.print(f"Loading baseline snapshot from [bold]{snapshot}[/bold]...")
        snap = DatasetSnapshot.load(snapshot)
    else:
        console.print(f"Creating [bold]{snap_mode}[/bold] snapshot of [bold]{p}[/bold]...")
        snap = create_snapshot(p, mode=snap_mode)
        if snapshot:
            snap.save(snapshot)
            console.print(f"Baseline snapshot saved to [bold]{snapshot}[/bold]")

    # 2. Verify
    result = verify(snap, target_path=p, mode=snap_mode)

    # 3. Print summary
    matched = len(result["matched"])
    modified = len(result["modified"])
    missing = len(result["missing"])
    added = len(result["added"])

    summary_table = Table(title="Dataset Drift Summary")
    summary_table.add_column("Category", style="bold")
    summary_table.add_column("Count", justify="right")

    match_style = "green" if modified == 0 and missing == 0 else "yellow"
    summary_table.add_row("Matched", f"[{match_style}]{matched}[/{match_style}]")
    if modified:
        summary_table.add_row("Modified", f"[yellow]{modified}[/yellow]")
    if missing:
        summary_table.add_row("Missing", f"[red]{missing}[/red]")
    if added:
        summary_table.add_row("Added", f"[blue]{added}[/blue]")

    console.print(summary_table)

    if modified:
        console.print("\n[bold yellow]Modified files:[/bold yellow]")
        for entry in result["modified"]:
            size_delta = entry["new_size"] - entry["old_size"]
            delta_str = f"{size_delta:+d}" if size_delta else ""
            console.print(f"  {entry['path']} ({entry['old_size']} -> {entry['new_size']} bytes {delta_str})")

    if missing:
        console.print("\n[bold red]Missing files:[/bold red]")
        for f in result["missing"]:
            console.print(f"  {f}")

    if added:
        console.print("\n[bold blue]Added files:[/bold blue]")
        for f in result["added"]:
            console.print(f"  {f}")

    # 4. Export
    if export:
        export_path = Path(export).expanduser().resolve()
        export_data = {
            "path": str(p),
            "snapshot_mode": snap_mode,
            "matched": matched,
            "modified": modified,
            "missing": missing,
            "added": added,
            "details": result,
        }
        export_path.write_text(json.dumps(export_data, indent=2, default=str))
        console.print(f"\nDiff report exported to [bold]{export_path}[/bold]")

    # 5. Check gates
    if gates:
        gates_path = Path(gates).expanduser().resolve()
        if not gates_path.exists():
            console.print(f"[red]Error:[/red] Gates file '{gates}' not found.")
            raise typer.Exit(code=1)

        gate_results = check_gates(str(gates_path), result)

        if not gate_results:
            console.print("\n[yellow]No gate checks could be performed.[/yellow]")
        else:
            gate_table = Table(title="Quality Gates")
            gate_table.add_column("Gate", style="bold")
            gate_table.add_column("Threshold", justify="right")
            gate_table.add_column("Actual", justify="right")
            gate_table.add_column("Status")

            all_passed = True
            for gr in gate_results:
                status = "[green]PASS[/green]" if gr.passed else "[red]FAIL[/red]"
                if not gr.passed:
                    all_passed = False
                gate_table.add_row(gr.name, str(gr.threshold), f"{gr.actual:.2f}", status)

            console.print(gate_table)

            if not all_passed:
                console.print("\n[red]Gate check FAILED.[/red]")
                raise typer.Exit(code=1)
            else:
                console.print("\n[green]All quality gates passed.[/green]")

    if modified or missing:
        logger.warning(f"Drift detected: {modified} modified, {missing} missing")
