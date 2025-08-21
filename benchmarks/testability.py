import subprocess
import json
import os
from .utils import get_python_files

def _secure_run(command, capture_output=True, text=True, check=False, cwd=None):
    """
    A small, secure wrapper around subprocess.run to reduce command injection risk
    and improve testability.

    - Validates that the command is provided as a sequence (list/tuple) of strings.
    - Checks for presence of a few common shell metacharacters in command arguments.
    - Forces shell=False when invoking subprocess.run.

    Parameters mirror subprocess.run for easy substitution in tests:
    - command: list or tuple of command and arguments.
    - capture_output, text, check, cwd: passed through to subprocess.run.

    Raises:
    - ValueError if command is not a safe sequence of strings.
    - TypeError if types are incorrect.
    """
    if not isinstance(command, (list, tuple)):
        raise TypeError("command must be a list or tuple of program and arguments (not a single string).")
    if len(command) == 0:
        raise ValueError("command must contain at least the program to execute.")

    forbidden_substrings = [";", "&&", "|", "$(", "`", ">", "<"]
    for part in command:
        if not isinstance(part, str):
            raise TypeError("each part of command must be a string")
        if any(sub in part for sub in forbidden_substrings):
            raise ValueError(f"potentially unsafe characters detected in command part: {part!r}")

    # Ensure cwd, if provided, is a string path (don't allow arbitrary objects)
    if cwd is not None and not isinstance(cwd, str):
        raise TypeError("cwd must be a string path or None")

    # Use shell=False explicitly to avoid shell interpretation
    return subprocess.run(command, capture_output=capture_output, text=text, check=check, cwd=cwd, shell=False)


def assess_testability(codebase_path: str, run_func=_secure_run):
    """
    Assess the testability of a codebase by running tests and measuring coverage.

    This function will:
    - Look for Python files in the provided codebase_path (using get_python_files).
    - Attempt to run pytest with coverage and output a JSON coverage report.
    - Parse the coverage report and return a score between 0 and 10 and a list of details.

    Parameters:
    - codebase_path: Path to the codebase to assess. This function validates that the path
      exists and is a directory before attempting to run subprocess commands.
    - run_func: Callable used to execute external commands. It should accept the same
      parameters as subprocess.run (command, capture_output, text, check, cwd). This
      parameter is provided to improve testability (can be mocked in unit tests).
      Default behavior uses a secure wrapper that enforces shell=False and validates inputs.

    Returns:
    - (score: float, details: List[str])
      score is between 0.0 and 10.0. details is a list of human-readable messages about the assessment.

    Notes:
    - The function attempts to remove the temporary coverage.json file it creates.
    - This function performs basic validation of codebase_path to avoid running commands in
      arbitrary locations.
    """
    details = []
    
    # Check for presence of test files
    python_files = get_python_files(codebase_path)
    test_files = (f for f in python_files if "test" in os.path.basename(f).lower())
    if not test_files:
        return 0.0, ["No test files found (e.g., files named test_*.py)."]

    json_report_path = os.path.join(codebase_path, "coverage.json")
    
    # Run pytest with coverage
    try:
        if not os.path.isdir(codebase_path):
            raise ValueError("Invalid or untrusted input path.")
        command = [
            "pytest",
            ''.join(['--cov=', codebase_path]),
            ''.join(['--cov-report=json:', json_report_path]),
            codebase_path
        ]
        run_func(command, capture_output=True, text=True, check=False, cwd=codebase_path)
    except FileNotFoundError:
        return 0.0, ["Could not run pytest. Is it installed and in your PATH?"]
    
    if not os.path.exists(json_report_path):
        return 0.0, ["Coverage report (coverage.json) was not generated. Tests may have failed."]

    try:
        with open(json_report_path) as f:
            report = json.load(f)
        
        coverage_percent = report.get("totals", {}).get("percent_covered", 0.0)
        details.append(f"Test coverage: {coverage_percent:.2f}%")
        
        # Scoring: 100% coverage = 10 points. 80% = 8 points, etc.
        score = coverage_percent / 10.0
        
        if coverage_percent < 50:
            details.append("Low coverage. Consider adding more tests for critical paths.")

    except (json.JSONDecodeError, FileNotFoundError):
        score = 0.0
        details.append("Could not parse coverage report.")
    finally:
        if os.path.exists(json_report_path):
            os.remove(json_report_path) # Clean up

    return min(10.0, max(0.0, score)), details