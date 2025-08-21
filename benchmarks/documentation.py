"""
Module for assessing documentation coverage and quality in a Python codebase.

Provides a public function `assess_documentation` which scans Python files
under a given path and reports coverage and a simple heuristic quality
measure for docstrings found on modules, classes and functions.

Heuristics:
- A "good" docstring is multi-line (>= 3 non-blank lines), mentions both
  arguments and returns (e.g. contains "Args:"/"Parameters:" and "Returns:"),
  and does not contain excessive consecutive blank lines.
"""

import ast
from typing import Tuple, List, Iterator, Optional
from .utils import get_python_files, parse_file

def assess_documentation(codebase_path: str) -> Tuple[float, List[str]]:
    """
    Assess documentation for a Python codebase.

    Scans all Python files found under `codebase_path` (using get_python_files)
    and parses each file's AST (using parse_file). For each module, class and
    function it checks for presence of a docstring and applies a heuristic
    to determine whether the docstring is "good".

    Returns a tuple of (score, details) where:
    - score is in range [0.0, 10.0]
    - details is a list of human-readable messages listing missing docstrings
      and summary lines at the top.

    The external signature is preserved; results and formatting are unchanged.
    """
    python_files = get_python_files(codebase_path)
    if not python_files:
        return 0.0, ["No Python files found."]

    total_entities = 0
    documented_entities = 0
    good_docstrings = 0
    details_acc: List[str] = []

    for file_path in python_files:
        tree = parse_file(file_path)
        if not tree:
            continue

        # Module docstring (compute once)
        total_entities += 1
        module_doc = ast.get_docstring(tree)
        if module_doc:
            documented_entities += 1
            if _good_docstring(module_doc):
                good_docstrings += 1
        else:
            details_acc.append(f"Missing docstring in module: {file_path}")

        # Walk tree once and handle documentable nodes
        for node, ds in _iter_documentable_nodes_with_doc(tree):
            total_entities += 1
            if ds:
                documented_entities += 1
                if _good_docstring(ds):
                    good_docstrings += 1
            else:
                details_acc.append(f"Missing docstring for '{node.name}' in {file_path}:{node.lineno}")

    if total_entities == 0:
        return 0.0, ["No documentable entities (classes, functions) found."]

    doc_coverage = (documented_entities / total_entities) * 100
    quality_ratio = (good_docstrings / documented_entities) if documented_entities else 0.0

    # Score components
    coverage_score = doc_coverage / 10.0  # 100% -> 10
    intrinsic_quality_score = quality_ratio * 10.0
    quality_score = intrinsic_quality_score

    final_score = (coverage_score + quality_score) / 2.0

    # Build final details list with summary lines up front
    summary_lines = [
        f"Documentation coverage: {doc_coverage:.2f}% ({documented_entities}/{total_entities})",
        f"Good docstrings: {good_docstrings}/{documented_entities} ({quality_ratio*100:.1f}%)"
    ]
    details = summary_lines + details_acc

    return min(10.0, max(0.0, final_score)), details

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _iter_documentable_nodes_with_doc(tree: ast.AST) -> Iterator[tuple]:
    """
    Iterate over functions, async functions and classes in the AST once.

    Yields tuples of (node, docstring_or_None). Avoids repeated calls to
    ast.walk() outside the iterator and ensures single-pass extraction.
    """
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield n, ast.get_docstring(n)

def _good_docstring(ds: str) -> bool:
    """
    Heuristic to determine whether a docstring is "good".

    Rules:
    - Must have at least 3 non-blank lines (e.g., short summary plus details).
    - Must not contain more than 5 consecutive blank lines.
    - Must mention both parameters (Args:/Parameters:) and returns (Returns:).
    """
    if not isinstance(ds, str):
        return False

    raw_lines = ds.splitlines()

    # Count non-blank lines efficiently using a generator
    non_blank_count = sum(1 for ln in raw_lines if ln.strip())
    if non_blank_count < 3:
        return False

    # Detect excessive consecutive blank lines
    consecutive_blanks = 0
    for ln in raw_lines:
        if ln.strip() == "":
            consecutive_blanks += 1
            if consecutive_blanks > 5:
                return False
        else:
            consecutive_blanks = 0

    lowered = ds.lower()
    has_args = any(k in lowered for k in ("args:", "parameters:"))
    has_returns = "returns:" in lowered

    return has_args and has_returns