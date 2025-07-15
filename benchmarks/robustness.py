
import ast
from .utils import get_python_files, parse_file

def assess_robustness(codebase_path: str):
    """
    Assesses the robustness of a codebase.
    - Checks for specific exception handling vs. generic `except:`.
    - Checks for the use of logging.
    """
    python_files = get_python_files(codebase_path)
    if not python_files:
        return 0.0, ["No Python files found."]

    total_handlers = 0
    good_handlers = 0
    uses_logging = False
    details = []

    nodes_with_file = [(node, file_path) for file_path in python_files if (tree := parse_file(file_path)) for node in ast.walk(tree)]
    
    for node, file_path in nodes_with_file:
        if isinstance(node, ast.Import) and any(alias.name == "logging" for alias in node.names):
            uses_logging = True
        elif isinstance(node, ast.ImportFrom) and node.module == "logging":
            uses_logging = True

        elif isinstance(node, ast.ExceptHandler):
            total_handlers += 1
            if node.type:
                if isinstance(node.type, ast.Name) and node.type.id == 'Exception':
                    details.append("".join(["Generic 'except Exception' used in ", str(file_path), ":", str(node.lineno)]))
                else:
                    good_handlers += 1
            else:
                details.append("".join(["Bare 'except:' used in ", str(file_path), ":", str(node.lineno)]))

    if uses_logging:
        details.insert(0, "Codebase appears to use the 'logging' module.")
    else:
        details.insert(0, "Codebase does not appear to use the 'logging' module.")

    if total_handlers == 0:
        return 5.0 if uses_logging else 2.0, details

    handler_quality = (good_handlers / total_handlers)
    handler_score = handler_quality * 8.0 # Max 8 points from handlers
    
    if uses_logging:
        handler_score += 2.0 # Bonus points for logging
    
    details.insert(1, f"Error handling quality: {handler_quality*100:.2f}% ({good_handlers}/{total_handlers} specific handlers)")

    return min(10.0, max(0.0, handler_score)), details 
