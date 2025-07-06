import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from pathlib import Path
import json
import os

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
    llm_score,
)
from benchmarks.db import record_run

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
    llm_score,
]

app = typer.Typer(context_settings={"help_option_names": ["-h", "--help"]})
console = Console()

# Dynamically collect benchmarks
def _load_benchmarks():
    mapping = {}
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

@app.command()
def compare(
    codebase1: Path = typer.Option(..., "--codebase1", "-c1", help="Path to the first codebase."),
    codebase2: Path = typer.Option(..., "--codebase2", "-c2", help="Path to the second codebase."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output with details for each benchmark."),
    weights: str = typer.Option('{}', "--weights", "-w", help='JSON string to weight benchmarks. e.g., \'{"Readability": 1.2, "Security": 0.8}\''),
    skip: str = typer.Option('', "--skip", help="Comma-separated list of benchmark names to skip."),
    export: Path = typer.Option(None, "--export", help="Path to write JSON export of results."),
    profile: Path = typer.Option(None, "--profile", help="Python script to execute for runtime profiling (pyinstrument)"),
):
    """
    Compares two codebases and rates them on a scale based on different benchmarks.
    """
    if not codebase1.is_dir() or not codebase2.is_dir():
        console.print("[bold red]Error: Both codebases must be valid directories.[/bold red]")
        raise typer.Exit(code=1)

    try:
        benchmark_weights = json.loads(weights)
    except json.JSONDecodeError:
        console.print("[bold red]Error: Invalid JSON format for weights.[/bold red]")
        raise typer.Exit(code=1)

    skip_set = {s.strip().capitalize() for s in skip.split(',') if s.strip()}

    # Set env for runtime profiling
    if profile:
        os.environ["BENCH_PROFILE_SCRIPT"] = str(profile)

    table = Table(title="Codebase Benchmark Comparison")
    table.add_column("Benchmark", justify="right", style="cyan", no_wrap=True)
    table.add_column(f"Codebase 1 ({codebase1.name})", justify="center", style="magenta")
    table.add_column(f"Codebase 2 ({codebase2.name})", justify="center", style="green")

    total_score1, total_score2 = 0, 0
    details1, details2 = {}, {}

    for name, func in BENCHMARK_FUNCS.items():
        if name in skip_set:
            continue

        weight = benchmark_weights.get(name, 1.0)
        
        score1, detail1 = func(str(codebase1))
        score2, detail2 = func(str(codebase2))
        
        weighted_score1 = score1 * weight
        weighted_score2 = score2 * weight

        details1[name] = detail1
        details2[name] = detail2

        total_score1 += weighted_score1
        total_score2 += weighted_score2

        table.add_row(name, f"{weighted_score1:.2f} (x{weight})", f"{weighted_score2:.2f} (x{weight})")
    
    table.add_row("---", "---", "---")
    table.add_row("[bold]Total Score[/bold]", f"[bold]{total_score1:.2f}[/bold]", f"[bold]{total_score2:.2f}[/bold]")
    
    console.print(table)

    # Store run for trend analysis
    record_run(str(codebase1), str(codebase2), total_score1, total_score2, {"details1": details1, "details2": details2})

    # Export if requested
    if export:
        export_data = {
            "codebase1": str(codebase1),
            "codebase2": str(codebase2),
            "score1": total_score1,
            "score2": total_score2,
            "details1": details1,
            "details2": details2,
        }
        os.makedirs(export.parent, exist_ok=True)
        export.write_text(json.dumps(export_data, indent=2))
        console.print(f"[green]Exported results to {export}")

    if verbose:
        console.print("\n[bold]Benchmark Details[/bold]")
        for name in BENCHMARK_FUNCS:
            if name in skip_set:
                continue
            p1 = Panel("\n".join(details1[name]) or "No issues found.", title=f"[cyan]{name} - {codebase1.name}", border_style="magenta")
            p2 = Panel("\n".join(details2[name]) or "No issues found.", title=f"[cyan]{name} - {codebase2.name}", border_style="green")
            console.print(p1)
            console.print(p2)


if __name__ == "__main__":
    app() 