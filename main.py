import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.live import Live
from rich.tree import Tree
from rich.text import Text
from rich.align import Align
from rich import box
from pathlib import Path
import json
import os
import time
from typing import Dict, List, Tuple, Callable, Any, Optional

# built-in benchmarks
from benchmarks import (
    readability,
    maintainability,
    performance,
    testability,
    robustness,
    security,
    scalability,
    documentation,
    consistency,
    git_health,
)
from benchmarks.db import record_run
from benchmarks.stats_utils import normalize_scores_zscore, BenchmarkResult

BUILT_IN_MODULES = [
    readability,
    maintainability,
    performance,
    testability,
    robustness,
    security,
    scalability,
    documentation,
    consistency,
    git_health,
]

app = typer.Typer(context_settings={"help_option_names": ["-h", "--help"]})
console = Console()


def _load_benchmarks() -> Dict[str, Callable[[str], Any]]:
    """
    Dynamically collect benchmark functions from the built-in modules.

    Returns a mapping from display name to the benchmark function.
    """
    mapping: Dict[str, Callable[[str], Any]] = {}
    for mod in BUILT_IN_MODULES:
        raw_name = mod.__name__.split(".")[-1]
        display_name = raw_name.replace("_", " ").title().replace(" ", "")  # e.g., git_health -> GitHealth
        func_name = f"assess_{raw_name}"
        if not hasattr(mod, func_name):
            # try camel variant (legacy)
            func_name_alt = func_name.replace("_", "")
            if hasattr(mod, func_name_alt):
                func_name = func_name_alt
        mapping[display_name] = getattr(mod, func_name)
    return mapping


BENCHMARK_FUNCS = _load_benchmarks()


def _prepare_benchmarks_list(skip_set: set) -> List[Tuple[str, Callable[[str], Any]]]:
    """
    Prepare a concrete list of benchmarks to run (filtered by skip set).
    Using a list avoids generator consumption issues and allows multiple passes.
    """
    return [(name, func) for name, func in BENCHMARK_FUNCS.items() if name not in skip_set]


def _extract_score_and_details(
    result: Any,
) -> Tuple[float, List[str], Dict[str, Any]]:
    """
    Normalize benchmark result to a score, details list and raw_metrics dict.
    Supports both legacy tuple-returning benchmarks and BenchmarkResult instances.
    """
    if isinstance(result, BenchmarkResult):
        score = result.score
        details = result.details
        raw_metrics = result.raw_metrics
    else:
        score, details = result
        raw_metrics = {}
    # Ensure details is a list for downstream processing
    if details is None:
        details_list: List[str] = []
    elif isinstance(details, list):
        details_list = details
    else:
        details_list = [str(details)]
    return score, details_list, raw_metrics


def _run_benchmarks(
    benchmarks_list: List[Tuple[str, Callable[[str], Any]]],
    codebase1: Path,
    codebase2: Path,
    benchmark_weights: Dict[str, float],
) -> Tuple[
    Dict[str, float],
    Dict[str, float],
    Dict[str, List[str]],
    Dict[str, List[str]],
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Any],
    Dict[str, Any],
]:
    """
    Execute all benchmarks and collect raw scores, details, raw metrics, and original results.

    Returns:
        raw_scores1, raw_scores2, details1, details2, raw_metrics1, raw_metrics2, raw_results1, raw_results2
    """
    raw_scores1: Dict[str, float] = {}
    raw_scores2: Dict[str, float] = {}
    details1: Dict[str, List[str]] = {}
    details2: Dict[str, List[str]] = {}
    raw_metrics1: Dict[str, Dict[str, Any]] = {}
    raw_metrics2: Dict[str, Dict[str, Any]] = {}
    raw_results1: Dict[str, Any] = {}
    raw_results2: Dict[str, Any] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        main_task = progress.add_task("Running quality analysis...", total=len(benchmarks_list))

        for name, func in benchmarks_list:
            progress.update(main_task, description=f"Analyzing {name.lower()}...")
            weight = benchmark_weights.get(name, 1.0)

            # Execute benchmarks once per codebase and store raw results for reuse
            res1 = func(str(codebase1))
            res2 = func(str(codebase2))

            raw_results1[name] = res1
            raw_results2[name] = res2

            score1, detail1_list, metrics1 = _extract_score_and_details(res1)
            score2, detail2_list, metrics2 = _extract_score_and_details(res2)

            raw_scores1[name] = score1
            raw_scores2[name] = score2
            details1[name] = detail1_list
            details2[name] = detail2_list
            raw_metrics1[name] = metrics1
            raw_metrics2[name] = metrics2

            progress.advance(main_task)
            time.sleep(0.1)  # Small delay for visual effect

    return raw_scores1, raw_scores2, details1, details2, raw_metrics1, raw_metrics2, raw_results1, raw_results2


def _format_score_display(
    result_obj: Any,
    weighted_score: float,
    weight: float,
) -> str:
    """
    Create a display string for a score, using the BenchmarkResult formatting when available.
    Appends a weight suffix when weight != 1.0 using a join to avoid repeated concatenation.
    """
    if isinstance(result_obj, BenchmarkResult):
        base_display = result_obj.format_score_with_ci()
    else:
        base_display = f"{weighted_score:.2f}"

    if weight != 1.0:
        # Use join to avoid repeated string concatenation
        return " ".join([base_display, f"(x{weight})"])
    return base_display


@app.command()
def compare(
    codebase1: Path = typer.Option(..., "--codebase1", "-c1", help="Path to the first codebase."),
    codebase2: Path = typer.Option(..., "--codebase2", "-c2", help="Path to the second codebase."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output with details for each benchmark."),
    weights: str = typer.Option('{}', "--weights", "-w", help='JSON string to weight benchmarks. e.g., \'{"Readability": 1.2, "Security": 0.8}\''),
    skip: str = typer.Option('', "--skip", help="Comma-separated list of benchmark names to skip."),
    export: Path = typer.Option(None, "--export", help="Path to write JSON export of results."),
    profile: Path = typer.Option(None, "--profile", help="Python script to execute for runtime profiling (pyinstrument)"),
) -> None:
    """
    Compares two codebases and rates them on a scale based on different benchmarks.

    This function orchestrates benchmark execution, normalization, result presentation,
    and optional export. It preserves the original command-line signature.
    """
    if not codebase1.is_dir() or not codebase2.is_dir():
        console.print("[bold red]Error: Both codebases must be valid directories.[/bold red]")
        raise typer.Exit(code=1)

    try:
        benchmark_weights: Dict[str, float] = json.loads(weights)
    except json.JSONDecodeError:
        console.print("[bold red]Error: Invalid JSON format for weights.[/bold red]")
        raise typer.Exit(code=1)

    skip_set = {s.strip().capitalize() for s in skip.split(',') if s.strip()}

    # Set env for runtime profiling
    if profile:
        os.environ["BENCH_PROFILE_SCRIPT"] = str(profile)

    # Welcome banner
    welcome_text = Text.assemble(
        ("🔍 OpenBase", "bold blue"),
        (" - Professional Codebase Quality Analysis", "bold white")
    )
    console.print(Align.center(welcome_text))
    console.print(Align.center(f"Comparing [magenta]{codebase1.name}[/magenta] vs [green]{codebase2.name}[/green]"))
    console.print()

    # Prepare benchmarks to run as a concrete list to allow multiple passes
    benchmarks_list = _prepare_benchmarks_list(skip_set)

    # Run benchmarks and collect raw results
    (
        raw_scores1,
        raw_scores2,
        details1,
        details2,
        raw_metrics1,
        raw_metrics2,
        raw_results1,
        raw_results2,
    ) = _run_benchmarks(benchmarks_list, codebase1, codebase2, benchmark_weights)

    console.print("✅ Analysis complete!\n")

    # Check for empty repositories
    if raw_scores1 and all(score == 0.0 for score in raw_scores1.values()):
        console.print(f"[yellow]Warning: {codebase1.name} appears to be empty or has no analyzable code.[/yellow]")
    if raw_scores2 and all(score == 0.0 for score in raw_scores2.values()):
        console.print(f"[yellow]Warning: {codebase2.name} appears to be empty or has no analyzable code.[/yellow]")

    # Apply z-score normalization to prevent metric dominance
    normalized_scores1 = normalize_scores_zscore(raw_scores1)
    normalized_scores2 = normalize_scores_zscore(raw_scores2)

    # Create enhanced results table
    table = Table(
        title="📊 Codebase Quality Comparison Results",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white on blue"
    )
    table.add_column("Benchmark", justify="right", style="cyan", no_wrap=True)
    table.add_column(f"🔵 {codebase1.name}", justify="center", style="magenta")
    table.add_column(f"🟢 {codebase2.name}", justify="center", style="green")
    table.add_column("Winner", justify="center", style="bold yellow")

    # Apply weights and calculate totals
    total_score1, total_score2 = 0.0, 0.0
    for name, func in benchmarks_list:
        weight = benchmark_weights.get(name, 1.0)
        weighted_score1 = normalized_scores1.get(name, 0.0) * weight
        weighted_score2 = normalized_scores2.get(name, 0.0) * weight

        # Accumulate total scores
        total_score1 += weighted_score1
        total_score2 += weighted_score2

        # Use stored raw result objects to avoid re-running benchmarks
        result1_obj = raw_results1.get(name)
        result2_obj = raw_results2.get(name)

        score1_display = _format_score_display(result1_obj, weighted_score1, weight)
        score2_display = _format_score_display(result2_obj, weighted_score2, weight)

        # Determine winner
        if weighted_score1 > weighted_score2:
            winner = "🔵"
        elif weighted_score2 > weighted_score1:
            winner = "🟢"
        else:
            winner = "🤝"

        table.add_row(name, score1_display, score2_display, winner)

    # Add separator and totals
    table.add_row("", "", "", "")

    # Overall winner
    if total_score1 > total_score2:
        overall_winner = "🔵 " + codebase1.name
        winner_style = "bold magenta"
    elif total_score2 > total_score1:
        overall_winner = "🟢 " + codebase2.name
        winner_style = "bold green"
    else:
        overall_winner = "🤝 Tie"
        winner_style = "bold yellow"

    table.add_row(
        "[bold]TOTAL SCORE[/bold]",
        f"[bold magenta]{total_score1:.2f}[/bold magenta]",
        f"[bold green]{total_score2:.2f}[/bold green]",
        f"[{winner_style}]{overall_winner}[/{winner_style}]"
    )

    console.print(table)

    # Summary panel
    score_diff = abs(total_score1 - total_score2)
    if score_diff > 10:
        assessment = "significantly better"
    elif score_diff > 5:
        assessment = "moderately better"
    elif score_diff > 2:
        assessment = "slightly better"
    else:
        assessment = "very similar to"

    summary_text = f"[bold]{overall_winner.split(' ', 1)[1] if ' ' in overall_winner else overall_winner}[/bold] is [bold]{assessment}[/bold] than the other codebase."
    summary_panel = Panel(
        summary_text,
        title="🎯 Summary",
        border_style="blue",
        padding=(1, 2)
    )
    console.print(summary_panel)

    # Store enhanced results
    enhanced_results = {
        "details1": details1,
        "details2": details2,
        "raw_metrics1": raw_metrics1,
        "raw_metrics2": raw_metrics2,
        "raw_scores1": raw_scores1,
        "raw_scores2": raw_scores2,
        "normalized_scores1": normalized_scores1,
        "normalized_scores2": normalized_scores2,
    }
    record_run(str(codebase1), str(codebase2), total_score1, total_score2, enhanced_results)

    # Export if requested
    if export:
        export_data = {
            "codebase1": str(codebase1),
            "codebase2": str(codebase2),
            "total_score1": total_score1,
            "total_score2": total_score2,
            **enhanced_results
        }
        os.makedirs(export.parent, exist_ok=True)
        export.write_text(json.dumps(export_data, indent=2))
        console.print(f"[green]Exported results to {export}")

    if verbose:
        console.print("\n" + "=" * 60)
        console.print(Align.center(Text("📋 Detailed Analysis Report", style="bold white on blue")))
        console.print("=" * 60)

        for name, _ in benchmarks_list:
            console.print(f"\n[bold cyan]🔍 {name} Analysis[/bold cyan]")

            # Create a tree structure for better organization
            tree = Tree(f"[bold]{name}[/bold]")

            # Add codebase 1 details
            cb1_branch = tree.add(f"[magenta]🔵 {codebase1.name}[/magenta] - Score: [bold]{normalized_scores1.get(name, 0.0):.2f}[/bold]")
            details1_content = details1.get(name) if details1.get(name) else ["✅ No issues found."]
            for detail in details1_content[:5]:  # Limit to first 5 items for readability
                cb1_branch.add(f"• {detail}")
            if len(details1_content) > 5:
                cb1_branch.add(f"[dim]... and {len(details1_content) - 5} more items[/dim]")

            # Add codebase 2 details
            cb2_branch = tree.add(f"[green]🟢 {codebase2.name}[/green] - Score: [bold]{normalized_scores2.get(name, 0.0):.2f}[/bold]")
            details2_content = details2.get(name) if details2.get(name) else ["✅ No issues found."]
            for detail in details2_content[:5]:
                cb2_branch.add(f"• {detail}")
            if len(details2_content) > 5:
                cb2_branch.add(f"[dim]... and {len(details2_content) - 5} more items[/dim]")

            console.print(tree)

            # Add interpretation
            score1 = normalized_scores1.get(name, 0.0)
            score2 = normalized_scores2.get(name, 0.0)
            if abs(score1 - score2) < 0.5:
                interpretation = "📊 Both codebases perform similarly in this area."
            elif score1 > score2:
                interpretation = f"📈 {codebase1.name} outperforms {codebase2.name} by {score1 - score2:.1f} points."
            else:
                interpretation = f"📈 {codebase2.name} outperforms {codebase1.name} by {score2 - score1:.1f} points."

            console.print(f"[dim]{interpretation}[/dim]")
            console.print()  # Add spacing


if __name__ == "__main__":
    app()