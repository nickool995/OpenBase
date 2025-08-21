import ast
import logging
from .utils import get_python_files, parse_file

logger = logging.getLogger(__name__)

def assess_robustness(codebase_path: str):
    """
    Assess the robustness of a Python codebase by analyzing exception handling and logging usage.

    Analysis performed:
    - Detects ExceptHandler nodes and classifies them as specific handlers vs. generic 'except Exception' or bare 'except:'.
    - Detects whether the 'logging' module is imported anywhere in the codebase.

    Returns a tuple (score: float, details: List[str]) where:
    - score is a heuristic 0.0-10.0 rating (higher is better).
    - details is a list of human-readable findings.

    Parameters:
    - codebase_path: Path to the root of the codebase (must be a string).

    Failure modes and notes:
    - If get_python_files fails (e.g., path does not exist or permissions error), the function returns (0.0, [error]).
    - If a file cannot be parsed (syntax error, decode error, IO error), that file is skipped and a message is appended to details.
    - The function logs exceptions with contextual information for better observability but preserves the original control-flow semantics.
    """
    if not isinstance(codebase_path, str):
        raise ValueError("codebase_path must be a string")

    # Attempt to enumerate Python files; log failures with context.
    try:
        python_files = get_python_files(codebase_path)
    except (OSError, ValueError) as e:
        logger.exception("Failed to list Python files for path=%s", codebase_path)
        return 0.0, [f"Error getting Python files: {e}"]
    except Exception as e:
        # Keep control-flow semantics (return error) but ensure the unexpected error is logged.
        logger.exception("Unexpected error while getting Python files for path=%s", codebase_path)
        return 0.0, [f"Error getting Python files: {e}"]

    if not python_files:
        return 0.0, ["No Python files found."]

    total_handlers = 0
    good_handlers = 0
    uses_logging = False
    details = []

    # Walk each file's AST once and collect both exception handling and logging import info.
    for file_path in python_files:
        try:
            tree = parse_file(file_path)
        except (SyntaxError, OSError, ValueError, UnicodeDecodeError) as e:
            # Known parse-related failures: append detail and continue; also log for diagnostics.
            logger.exception("Failed to parse file=%s", file_path)
            details.append("Error parsing {}: {}".format(file_path, e))
            continue
        except Exception as e:
            # Unexpected parse error: preserve original behavior (report and continue) but log it.
            logger.exception("Unexpected error parsing file=%s", file_path)
            details.append("Error parsing {}: {}".format(file_path, e))
            continue

        if tree:
            # Use a single AST walk to avoid repeated traversal (performance improvement).
            for node in ast.walk(tree):
                # Inspect exception handlers
                if isinstance(node, ast.ExceptHandler):
                    total_handlers += 1
                    if node.type:
                        # Specific exception type is provided; flag overly generic catch of 'Exception'.
                        if isinstance(node.type, ast.Name) and node.type.id == 'Exception':
                            details.append("Generic 'except Exception' used in {}:{}".format(file_path, node.lineno))
                        else:
                            good_handlers += 1
                    else:
                        # Bare except: (catch-all) - record for maintainers.
                        details.append("Bare 'except:' used in {}:{}".format(file_path, node.lineno))

                # Inspect imports for logging usage
                if isinstance(node, ast.Import):
                    # any(alias.name == "logging" for alias in node.names)
                    for alias in node.names:
                        if alias.name == "logging":
                            uses_logging = True
                            # Once logging is detected in this file, no need to repeatedly set flag.
                            break
                elif isinstance(node, ast.ImportFrom):
                    if node.module == "logging":
                        uses_logging = True

    if uses_logging:
        details.insert(0, "Codebase appears to use the 'logging' module.")
    else:
        details.insert(0, "Codebase does not appear to use the 'logging' module.")

    if total_handlers == 0:
        # If no handlers found, provide a lower baseline score but slightly higher if logging is used.
        return 5.0 if uses_logging else 2.0, details

    handler_quality = (good_handlers / total_handlers)
    handler_score = handler_quality * 8.0  # Max 8 points from handlers

    if uses_logging:
        handler_score += 2.0  # Bonus points for logging

    # Provide a concise summary inserted near the top of details.
    details.insert(1, "Error handling quality: {:.2f}% ({}/{})".format(handler_quality * 100, good_handlers, total_handlers))

    return min(10.0, max(0.0, handler_score)), details