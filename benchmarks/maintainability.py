from radon.metrics import mi_visit
from .utils import get_python_files

def assess_maintainability(codebase_path: str):
    """
    Assesses the maintainability of a codebase using the Maintainability Index (MI).
    A higher MI score is better.
    """
    python_files = get_python_files(codebase_path)
    if not python_files:
        return 0.0, ["No Python files found."]

    total_mi = 0
    file_count = 0
    details = []
    
    for file_path in python_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        if code.strip():
            try:
                mi = mi_visit(code, multi=True)
                if mi < 40:
                    details.append(f"Low maintainability index ({mi:.2f}) in {file_path}")
                total_mi += mi
                file_count += 1
            except Exception:
                details.append(f"Could not parse {file_path}")

    avg_mi = (total_mi / file_count) if file_count > 0 else 0
    details.insert(0, f"Average maintainability index (MI): {avg_mi:.2f} (higher is better)")
    
    maintainability_score = avg_mi / 10.0
    
    return min(10.0, max(0.0, maintainability_score)), details 