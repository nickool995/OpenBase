
from radon.visitors import ComplexityVisitor
from pycodestyle import StyleGuide
from .utils import get_python_files

def assess_readability(codebase_path: str):
    """
    Assesses the readability of a codebase.
    - Cyclomatic Complexity: Lower is better.
    - PEP8 Compliance: Fewer errors is better.
    """
    python_files = get_python_files(codebase_path)
    if not python_files:
        return 0.0, ["No Python files found."]

    details = []
    total_complexity = 0
    total_functions = 0
    # Loop through each Python file to analyze functions
    for file_path in python_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        try:
            visitor = ComplexityVisitor.from_code(code)
            # Loop through functions in the file to check and accumulate complexity
            # This helps in identifying high complexity functions and calculating averages
            for f in visitor.functions:
                if f.complexity > 10:
                    details.append(f"High complexity ({f.complexity}) in function '{f.name}' at {file_path}:{f.lineno}")
                total_complexity += f.complexity
                total_functions += 1
        except (SyntaxError, ImportError):  # Handle specific exceptions related to code parsing
            pass  # Ignore files that can't be parsed due to syntax or import issues

    avg_complexity = (total_complexity / total_functions) if total_functions > 0 else 0
    complexity_score = max(0, 10 - (avg_complexity - 5))
    details.append(f"Average cyclomatic complexity: {avg_complexity:.2f}")

    style_guide = StyleGuide(quiet=True)
    report = style_guide.check_files(python_files)
    pep8_errors = report.total_errors
    details.append(f"Found {pep8_errors} PEP8 style violations.")
    
    pep8_score = max(0, 10 - (pep8_errors / 5))
    
    readability_score = (0.6 * complexity_score + 0.4 * pep8_score)  # Calculate final readability score based on weighted average
    
    return min(10.0, max(0.0, readability_score)), details 
