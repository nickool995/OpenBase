import subprocess
import json
import os
import time
from typing import List, Dict, Any, Optional
from .utils import get_python_files
from .stats_utils import BenchmarkResult, calculate_confidence_interval, adjust_score_for_size, get_codebase_size_bucket
import tempfile  # Added for secure temp file handling
import logging  # Added for proper logging

logging.basicConfig(level=logging.INFO)  # Configure basic logging

# Whitelist of allowed top-level commands for subprocess execution.
# Assumption: Only these CLI tools are expected to be invoked by this module.
_ALLOWED_TOP_CMDS = {"bandit", "safety", "docker"}


def _run_command(command: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """
    Run an external command safely using subprocess.run with shell=False.
    Performs lightweight validation:
      - command must be a non-empty list of strings
      - top-level executable must be in a small whitelist of allowed commands
    Returns the CompletedProcess instance.
    """
    if not isinstance(command, list) or not command:
        raise ValueError("command must be a non-empty list")
    if not all(isinstance(p, str) for p in command):
        raise ValueError("all command parts must be strings")
    top = command[0]
    if top not in _ALLOWED_TOP_CMDS:
        raise ValueError(f"Command '{top}' is not allowed")
    # Use shell=False implicitly by passing a list to subprocess.run
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def assess_security(codebase_path: str) -> BenchmarkResult:
    """
    Hybrid static + dynamic security assessment.
    Combines bandit/safety with optional OWASP ZAP dynamic scanning.
    """
    details = []
    raw_metrics = {}
    
    # === STATIC ANALYSIS ===
    static_score, static_details, static_metrics = _assess_static_security(codebase_path)
    details.extend(static_details)
    raw_metrics.update(static_metrics)
    
    # === DYNAMIC ANALYSIS ===
    web_app_url = os.getenv("BENCH_WEB_APP_URL")  # e.g., http://localhost:8000
    if web_app_url:
        # Validate untrusted input for web_app_url
        if not web_app_url.startswith('http'):
            logging.error(f"Invalid web_app_url: {web_app_url}")
            raise ValueError("Invalid URL provided")
        dynamic_score, dynamic_details, dynamic_metrics = _assess_dynamic_security(web_app_url)
        details.extend(dynamic_details)
        raw_metrics.update(dynamic_metrics)
        
        # Combine static + dynamic (weighted)
        final_score = (0.6 * static_score) + (0.4 * dynamic_score)
    else:
        final_score = static_score
        details.append("No web app URL provided (set BENCH_WEB_APP_URL). Using static analysis only.")
    
    # === BIAS ADJUSTMENT ===
    size_bucket = get_codebase_size_bucket(codebase_path)
    adjusted_score = adjust_score_for_size(final_score, size_bucket, "security")
    raw_metrics["size_bucket"] = size_bucket
    raw_metrics["unadjusted_score"] = final_score
    
    # === CONFIDENCE INTERVAL ===
    score_samples = [static_score]
    if "dynamic_score" in raw_metrics:
        score_samples.append(raw_metrics["dynamic_score"])
    
    confidence_interval = calculate_confidence_interval(score_samples)
    
    return BenchmarkResult(
        score=adjusted_score,
        details=details,
        raw_metrics=raw_metrics,
        confidence_interval=confidence_interval
    )


def _assess_static_security(codebase_path: str) -> tuple[float, List[str], Dict[str, Any]]:
    """Static security analysis with bandit and safety."""
    details = []
    metrics = {}
    
    # Validate untrusted input for codebase_path
    if not os.path.isdir(codebase_path):
        logging.error(f"Invalid codebase_path: {codebase_path}")
        raise ValueError("Invalid directory provided")
    
    # --- Bandit Scan ---
    bandit_score = 10.0
    try:
        command = ["bandit", "-r", codebase_path, "-f", "json"]
        result = _run_command(command)  # Line 65: use wrapper
        report = json.loads(result.stdout)
        
        if report and "results" in report:
            findings = report["results"]
            high = sum(1 for f in findings if f["issue_severity"] == "HIGH")
            medium = sum(1 for f in findings if f["issue_severity"] == "MEDIUM")
            low = sum(1 for f in findings if f["issue_severity"] == "LOW")
            
            details.append(f"[Bandit] High: {high}, Medium: {medium}, Low: {low}")
            metrics["bandit_high"] = high
            metrics["bandit_medium"] = medium
            metrics["bandit_low"] = low

            for f in findings[:10]:  # Limit to first 10
                details.append(f"  - {f['issue_text']} ({f['filename']}:{f['line_number']})")

            score_deduction = (high * 3) + (medium * 1) + (low * 0.5)
            bandit_score = max(0.0, 10.0 - score_deduction)
    except (json.JSONDecodeError, FileNotFoundError, ValueError) as e:
        logging.error(f"Error in Bandit scan: {e}")
        details.append("[Bandit] Could not run bandit.")
        bandit_score = 0.0

    # --- Safety Scan ---
    safety_score = 10.0
    req_file = os.path.join(codebase_path, "requirements.txt")
    if os.path.exists(req_file):
        try:
            # Defensive check: ensure requirements.txt resides within the provided codebase_path
            if os.path.commonpath([os.path.abspath(req_file), os.path.abspath(codebase_path)]) != os.path.abspath(codebase_path):
                logging.error("requirements.txt is outside the codebase path")
                raise ValueError("Invalid requirements.txt location")
            command = ["safety", "check", f"--file={req_file}", "--json"]
            result = _run_command(command)  # Line 94: use wrapper
            report = json.loads(result.stdout)
            
            vulns = len(report)
            details.append(f"[Safety] {vulns} vulnerable dependencies")
            metrics["safety_vulnerabilities"] = vulns
            
            for vuln in report[:5]:  # Limit output
                details.append(f"  - {vuln['package_name']}: {vuln['advisory'][:100]}...")
            
            safety_score = max(0.0, 10.0 - (vulns * 2))
        except (json.JSONDecodeError, FileNotFoundError, ValueError) as e:
            logging.error(f"Error in Safety scan: {e}")
            details.append("[Safety] Could not run safety.")
            safety_score = 5.0
    else:
        details.append("[Safety] No requirements.txt found.")
        safety_score = 8.0  # Neutral if no deps to check

    # Combine static scores
    static_score = (bandit_score * 0.7) + (safety_score * 0.3)
    metrics["bandit_score"] = bandit_score
    metrics["safety_score"] = safety_score
    
    return static_score, details, metrics


def _assess_dynamic_security(web_app_url: str) -> tuple[float, List[str], Dict[str, Any]]:
    """Dynamic security testing with OWASP ZAP (if available)."""
    details = []
    metrics = {}
    
    # Check if ZAP is available
    tmpfile = None
    try:
        tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        command = [
            "docker", "run", "--rm", "-t",
            "owasp/zap2docker-stable",
            "zap-baseline.py",
            "-t", web_app_url,
            "-J", tmpfile.name  # Line 133: Fixed to use secure temp file
        ]
        
        details.append(f"[ZAP] Running baseline scan on {web_app_url}")
        
        # Run with timeout
        result = _run_command(command, timeout=120)  # Line 139: use wrapper
        
        # Clean up temp file
        try:
            os.remove(tmpfile.name)
        except Exception:
            pass
        
        # ZAP returns non-zero on findings, so check output instead
        if "PASS" in result.stdout or "WARN" in result.stdout:
            # Count severity levels from output
            high_count = result.stdout.count("HIGH")
            medium_count = result.stdout.count("MEDIUM") 
            low_count = result.stdout.count("LOW")
            
            details.append(f"[ZAP] Findings - High: {high_count}, Medium: {medium_count}, Low: {low_count}")
            
            metrics["zap_high"] = high_count
            metrics["zap_medium"] = medium_count
            metrics["zap_low"] = low_count
            
            # Score based on findings
            score_deduction = (high_count * 4) + (medium_count * 2) + (low_count * 0.5)
            dynamic_score = max(0.0, 10.0 - score_deduction)
            
        else:
            details.append("[ZAP] Scan completed but could not parse results")
            dynamic_score = 5.0
            
    except subprocess.TimeoutExpired as e:
        logging.error(f"ZAP scan timed out: {e}")
        details.append("[ZAP] Scan timed out (>2 min)")
        dynamic_score = 3.0
    except FileNotFoundError as e:
        logging.error(f"ZAP Docker not available: {e}")
        details.append("[ZAP] Docker/ZAP not available. Install: docker pull owasp/zap2docker-stable")
        dynamic_score = 5.0  # Neutral if tool unavailable
    except ValueError as e:
        logging.error(f"ZAP invocation blocked: {e}")
        details.append("[ZAP] Invocation blocked due to unsafe command or parameters.")
        dynamic_score = 3.0
    except Exception as e:
        logging.error(f"Error in ZAP scan: {e}")
        details.append(f"[ZAP] Error: {e}")
        dynamic_score = 3.0
    finally:
        # Ensure temp file cleaned up if still present
        if tmpfile is not None:
            try:
                if os.path.exists(tmpfile.name):
                    os.remove(tmpfile.name)
            except Exception:
                pass
    
    metrics["dynamic_score"] = dynamic_score
    return dynamic_score, details, metrics