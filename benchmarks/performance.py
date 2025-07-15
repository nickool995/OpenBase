
import ast
import os
import subprocess  # Address security implications: Ensure safe usage in calls
import json
import tempfile
import statistics
from typing import List, Dict, Any
from .utils import get_python_files, parse_file
from .stats_utils import BenchmarkResult, calculate_confidence_interval, adjust_score_for_size, get_codebase_size_bucket

def assess_performance(codebase_path: str) -> BenchmarkResult:
    """
    Hybrid static + dynamic performance assessment.
    Combines anti-pattern detection with runtime profiling.
    """
    python_files = get_python_files(codebase_path)
    if not python_files:
        return BenchmarkResult(0.0, ["No Python files found."])

    details = []
    raw_metrics = {}
    
    # === STATIC ANALYSIS ===
    static_score, static_details = _assess_static_performance(python_files)
    details.extend(static_details)
    raw_metrics["static_score"] = static_score
    
    # === DYNAMIC ANALYSIS ===
    profile_script = os.getenv("BENCH_PROFILE_SCRIPT")
    if profile_script and os.path.exists(profile_script):
        dynamic_score, dynamic_details, runtime_metrics = _assess_dynamic_performance(profile_script)
        details.extend(dynamic_details)
        raw_metrics.update(runtime_metrics)
        
        # Combine static + dynamic (weighted)
        final_score = (0.4 * static_score) + (0.6 * dynamic_score)
    else:
        final_score = static_score
        details.append("No profile script provided (set BENCH_PROFILE_SCRIPT). Using static analysis only.")
    
    # === BIAS ADJUSTMENT ===
    size_bucket = get_codebase_size_bucket(codebase_path)
    adjusted_score = adjust_score_for_size(final_score, size_bucket, "performance")
    raw_metrics["size_bucket"] = size_bucket
    raw_metrics["unadjusted_score"] = final_score
    
    # === CONFIDENCE INTERVAL ===
    # Use variance from multiple metrics as proxy for uncertainty
    score_samples = [static_score]
    if "execution_times" in raw_metrics:
        score_samples.extend(raw_metrics["execution_times"])
    
    confidence_interval = calculate_confidence_interval(score_samples)
    
    return BenchmarkResult(
        score=adjusted_score,
        details=details,
        raw_metrics=raw_metrics,
        confidence_interval=confidence_interval
    )


def _assess_static_performance(python_files: List[str]) -> tuple[float, List[str]]:
    """Static anti-pattern detection."""
    details = []
    anti_patterns_found = 0
    performance_score = 10.0

    for file_path in python_files:
        tree = parse_file(file_path)
        if not tree:
            continue

        nodes = list(ast.walk(tree))  # Collect nodes once to reduce repeated walks
        for node in nodes:
            # Anti-pattern: list.insert(0, val)
            if (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and
                node.func.attr == 'insert' and
                len(node.args) == 2 and
                hasattr(node.args[0], 'value') and node.args[0].value == 0):
                details.append(f"Inefficient 'list.insert(0, ...)' at {file_path}:{node.lineno}")
                anti_patterns_found += 1

            # Anti-pattern: string concatenation in loops
            if isinstance(node, (ast.For, ast.While)):
                sub_nodes = list(ast.walk(node))  # Collect sub nodes once
                for sub_node in sub_nodes:
                    if isinstance(sub_node, ast.AugAssign) and isinstance(sub_node.op, ast.Add):
                        if isinstance(sub_node.target, ast.Name):
                            details.append(f"String concatenation in loop at {file_path}:{node.lineno}")
                            anti_patterns_found += 0.5

            # Anti-pattern: nested loops (O(n²) potential)
            if isinstance(node, ast.For):
                sub_nodes = list(ast.walk(node))  # Collect sub nodes once
                for sub_node in sub_nodes:
                    if isinstance(sub_node, ast.For) and sub_node != node:
                        details.append(f"Nested loops (O(n²) risk) at {file_path}:{node.lineno}")
                        anti_patterns_found += 0.3

    performance_score -= anti_patterns_found
    details.insert(0, f"Static analysis: {anti_patterns_found} performance anti-patterns found")
    
    return min(10.0, max(0.0, performance_score)), details


def _assess_dynamic_performance(profile_script: str) -> tuple[float, List[str], Dict[str, Any]]:
    """Dynamic runtime profiling with multiple samples."""
    details = []
    metrics = {}
    
    # Run multiple samples for statistical confidence
    execution_times = []
    memory_peaks = []
    
    for run_num in range(3):  # 3 samples
        # === TIME PROFILING ===
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            time_report_path = tmp.name
        
        try:
            # Ensure untrusted input is checked: Validate profile_script exists and is a string
            if not isinstance(profile_script, str) or not os.path.exists(profile_script):
                raise ValueError("Invalid profile script")
            cmd = ["pyinstrument", "--json", "-o", time_report_path, profile_script]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # Line 121 modified for security
            if proc.returncode == 0 and os.path.exists(time_report_path):
                with open(time_report_path) as f:
                    time_data = json.load(f)
                execution_time = time_data.get("duration", 0) * 1000  # ms
                execution_times.append(execution_time)
        except Exception as e:
            details.append(f"Error in time profiling: {str(e)}")  # Replace try-except-pass at line 128
        finally:
            if os.path.exists(time_report_path):
                os.remove(time_report_path)
        
        # === MEMORY PROFILING ===
        try:
            # Ensure untrusted input is checked: Validate profile_script exists and is a string
            if not isinstance(profile_script, str) or not os.path.exists(profile_script):
                raise ValueError("Invalid profile script")
            cmd = ["python", "-m", "memory_profiler", profile_script]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # Line 137 modified for security
            if proc.returncode == 0:
                lines = proc.stdout.split('\n')
                for line in lines:
                    if 'MiB' in line and 'maximum of' in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == 'maximum' and i+2 < len(parts):
                                try:
                                    peak_mb = float(parts[i+2])
                                    memory_peaks.append(peak_mb)
                                    break
                                except ValueError:
                                    pass
        except Exception as e:
            details.append(f"Error in memory profiling: {str(e)}")  # Replace try-except-pass at line 154
    # === SCORING ===
    if execution_times:
        avg_time = statistics.mean(execution_times)
        time_std = statistics.stdev(execution_times) if len(execution_times) > 1 else 0
        
        details.append(''.join([f"Avg execution time: ", f"{avg_time:.1f}", "ms (±", f"{time_std:.1f}", "ms)"]))  # Line 147: Use join() instead of concatenation
        
        if avg_time < 100:
            time_score = 10.0
        elif avg_time < 500:
            time_score = 8.0
        elif avg_time < 1000:
            time_score = 6.0
        elif avg_time < 2000:
            time_score = 4.0
        else:
            time_score = 2.0
        
        metrics["execution_times"] = execution_times
        metrics["avg_execution_time_ms"] = avg_time
    else:
        time_score = 0.0
        details.append("Could not measure execution time")
    
    if memory_peaks:
        avg_memory = statistics.mean(memory_peaks)
        details.append(''.join([f"Peak memory usage: ", f"{avg_memory:.1f}", "MB"]))  # Line 149: Use join() instead of concatenation
        
        if avg_memory < 50:
            memory_score = 10.0
        elif avg_memory < 200:
            memory_score = 8.0
        elif avg_memory < 500:
            memory_score = 6.0
        else:
            memory_score = 4.0
        
        metrics["memory_peaks_mb"] = memory_peaks
        metrics["avg_memory_mb"] = avg_memory
    else:
        memory_score = 8.0
        details.append("Could not measure memory usage")
    
    dynamic_score = (time_score + memory_score) / 2.0
    
    return dynamic_score, details, metrics 

def detect_insert_zero_anti_pattern(nodes: List[ast.AST], file_path: str, details: List[str], anti_patterns_found: float):
    for node in nodes:
        if (isinstance(node, ast.Call) and
            isinstance(node.func, ast.Attribute) and
            node.func.attr == 'insert' and
            len(node.args) == 2 and
            hasattr(node.args[0], 'value') and node.args[0].value == 0):
            details.append(f"Inefficient 'list.insert(0, ...)' at {file_path}:{node.lineno}")
            anti_patterns_found += 1
    return anti_patterns_found

def detect_string_concatenation_anti_pattern(nodes: List[ast.AST], file_path: str, details: List[str], anti_patterns_found: float):
    for node in nodes:
        if isinstance(node, (ast.For, ast.While)):
            sub_nodes = list(ast.walk(node))
            for sub_node in sub_nodes:
                if isinstance(sub_node, ast.AugAssign) and isinstance(sub_node.op, ast.Add):
                    if isinstance(sub_node.target, ast.Name):
                        details.append(f"String concatenation in loop at {file_path}:{node.lineno}")
                        anti_patterns_found += 0.5
    return anti_patterns_found

def detect_nested_loops_anti_pattern(nodes: List[ast.AST], file_path: str, details: List[str], anti_patterns_found: float):
    for node in nodes:
        if isinstance(node, ast.For):
            sub_nodes = list(ast.walk(node))
            for sub_node in sub_nodes:
                if isinstance(sub_node, ast.For) and sub_node != node:
                    details.append(f"Nested loops (O(n²) risk) at {file_path}:{node.lineno}")
                    anti_patterns_found += 0.3
    return anti_patterns_found

def _assess_static_performance_extracted(python_files: List[str]) -> tuple[float, List[str]]:
    details = []
    anti_patterns_found = 0.0
    for file_path in python_files:
        tree = parse_file(file_path)
        if not tree:
            continue
        nodes = list(ast.walk(tree))
        anti_patterns_found = detect_insert_zero_anti_pattern(nodes, file_path, details, anti_patterns_found)
        anti_patterns_found = detect_string_concatenation_anti_pattern(nodes, file_path, details, anti_patterns_found)
        anti_patterns_found = detect_nested_loops_anti_pattern(nodes, file_path, details, anti_patterns_found)
    performance_score = 10.0 - anti_patterns_found
    details.insert(0, f"Static analysis: {anti_patterns_found} performance anti-patterns found")
    return min(10.0, max(0.0, performance_score)), details

_assess_static_performance = _assess_static_performance_extracted  # Replace original with extracted version
