import ast
from .utils import get_python_files, parse_file
import os, subprocess, json, tempfile

def assess_performance(codebase_path: str):
    """
    Assesses performance by checking for common static anti-patterns.
    This is a simplified analysis and not a substitute for profiling.
    """
    profile_script = os.getenv("BENCH_PROFILE_SCRIPT")
    if profile_script:
        # Run pyinstrument to capture wall time JSON report
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            out_path = tmp.name
        try:
            cmd = ["pyinstrument", "--json", "-o", out_path, profile_script]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                return 0.0, ["Profiling script failed to run.", proc.stderr]
            with open(out_path) as f:
                data = json.load(f)
            total_ms = data.get("duration", 0) * 1000
            details = [f"Profiled runtime: {total_ms:.1f} ms"]
            # Scoring: <200ms => 10, 200-500ms => 8, 500-1000ms => 6, else scaled down
            if total_ms < 200:
                score = 10.0
            elif total_ms < 500:
                score = 8.0
            elif total_ms < 1000:
                score = 6.0
            elif total_ms < 2000:
                score = 4.0
            else:
                score = 2.0
            return score, details
        finally:
            try:
                os.remove(out_path)
            except OSError:
                pass

    # Fallback to static analysis
    python_files = get_python_files(codebase_path)
    if not python_files:
        return 0.0, ["No Python files found."]

    details = []
    anti_patterns_found = 0
    
    performance_score = 10.0

    for file_path in python_files:
        tree = parse_file(file_path)
        if not tree:
            continue

        for node in ast.walk(tree):
            # Anti-pattern: using list.insert(0, val)
            if (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and
                node.func.attr == 'insert' and
                len(node.args) == 2 and
                hasattr(node.args[0], 'value') and node.args[0].value == 0):
                details.append(f"Inefficient 'list.insert(0, ...)' used in {file_path}:{node.lineno}. Consider collections.deque.")
                anti_patterns_found += 1

            # Anti-pattern: string concatenation in a loop
            if isinstance(node, (ast.For, ast.While)):
                for sub_node in ast.walk(node):
                    if isinstance(sub_node, ast.AugAssign) and isinstance(sub_node.op, ast.Add):
                        # Heuristic: check if the target is likely a string
                        if isinstance(sub_node.target, ast.Name):
                            details.append(f"String concatenation in a loop in {file_path}:{node.lineno}. Consider ''.join().")
                            anti_patterns_found += 0.5 # Less severe

    performance_score -= anti_patterns_found
    details.insert(0, f"Found {anti_patterns_found} potential performance anti-patterns.")
    
    return min(10.0, max(0.0, performance_score)), details 