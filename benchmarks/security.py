import subprocess
import json
import os
from .utils import get_python_files

def assess_security(codebase_path: str):
    """
    Assesses the security of a codebase using bandit and safety.
    """
    details = []
    
    # --- Bandit Scan ---
    bandit_score = 10.0
    try:
        command = ["bandit", "-r", codebase_path, "-f", "json"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        report = json.loads(result.stdout)
        
        if report and "results" in report:
            findings = report["results"]
            high = sum(1 for f in findings if f["issue_severity"] == "HIGH")
            medium = sum(1 for f in findings if f["issue_severity"] == "MEDIUM")
            low = sum(1 for f in findings if f["issue_severity"] == "LOW")
            
            details.append(f"[Bandit] High-sev findings: {high}")
            details.append(f"[Bandit] Medium-sev findings: {medium}")
            details.append(f"[Bandit] Low-sev findings: {low}")

            for f in findings:
                details.append(f"  - {f['issue_text']} ({f['filename']}:{f['line_number']})")

            score_deduction = (high * 3) + (medium * 1) + (low * 0.5)
            bandit_score = max(0.0, 10.0 - score_deduction)
    except (json.JSONDecodeError, FileNotFoundError):
        details.append("[Bandit] Could not run or parse bandit output.")
        bandit_score = 0.0

    # --- Safety Scan ---
    safety_score = 10.0
    req_file = os.path.join(codebase_path, "requirements.txt")
    if os.path.exists(req_file):
        try:
            command = ["safety", "check", f"--file={req_file}", "--json"]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            report = json.loads(result.stdout)
            
            vulns = len(report)
            details.append(f"[Safety] Found {vulns} vulnerable dependencies.")
            for vuln in report:
                details.append(f"  - {vuln['package_name']} {vuln['affected_versions']}: {vuln['description']}")
            
            safety_score = max(0.0, 10.0 - (vulns * 2))
        except (json.JSONDecodeError, FileNotFoundError):
            details.append("[Safety] Could not run or parse safety output.")
            safety_score = 0.0
    else:
        details.append("[Safety] No requirements.txt found, skipping dependency scan.")

    # Combine scores (70% bandit, 30% safety)
    final_score = (bandit_score * 0.7) + (safety_score * 0.3)
    
    return min(10.0, max(0.0, final_score)), details 