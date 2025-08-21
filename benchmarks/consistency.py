import ast
import re
import io
from typing import Tuple, List
from .utils import get_python_files, parse_file

SNAKE_CASE_REGEX = re.compile(r"^[a-z_][a-z0-9_]*$")
CAMEL_CASE_REGEX = re.compile(r"^[A-Z][a-zA-Z0-9]*$")

def assess_consistency(codebase_path: str) -> Tuple[float, List[str]]:
    """
    Assess the naming consistency within a Python codebase.

    Rules:
    - Class names should be CamelCase.
    - Function and variable names should be snake_case.

    Returns:
    - A tuple of (score, details) where score is between 0.0 and 10.0 and
      details is a list of human-readable messages describing inconsistencies
      or notable conditions (e.g., no files found).
    """
    python_files = get_python_files(codebase_path)
    if not python_files:
        return 0.0, ["No Python files found."]

    def _format_inconsistency_message(kind: str, identifier: str, file_path: str, lineno: int, case_description: str) -> str:
        """
        Build an inconsistency message in a memory-efficient way using StringIO.

        Example output:
        "Inconsistent class name: 'MyClass' should be CamelCase. (path/to/file.py:10)"
        """
        buf = io.StringIO()
        buf.write("Inconsistent ")
        buf.write(kind)
        buf.write(": '")
        buf.write(identifier)
        buf.write("' should be ")
        buf.write(case_description)
        buf.write(". (")
        buf.write(file_path)
        buf.write(":")
        buf.write(str(lineno))
        buf.write(")")
        return buf.getvalue()

    total_names = 0
    inconsistent_names = 0
    details: List[str] = []

    for file_path in python_files:
        tree = parse_file(file_path)
        if not tree:
            continue

        class ConsistencyVisitor(ast.NodeVisitor):
            def __init__(self, file_path):
                self.file_path = file_path
                self.total_names = 0
                self.inconsistent_names = 0
                self.details: List[str] = []

            def visit_ClassDef(self, node):
                self.total_names += 1
                if not CAMEL_CASE_REGEX.match(node.name):
                    self.inconsistent_names += 1
                    self.details.append(_format_inconsistency_message("class name", node.name, self.file_path, node.lineno, "CamelCase"))

            def visit_FunctionDef(self, node):
                if not node.name.startswith("__") and not SNAKE_CASE_REGEX.match(node.name):
                    self.total_names += 1
                    self.inconsistent_names += 1
                    self.details.append(_format_inconsistency_message("function name", node.name, self.file_path, node.lineno, "snake_case"))

            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Store):
                    self.total_names += 1
                    if not SNAKE_CASE_REGEX.match(node.id):
                        self.inconsistent_names += 1
                        self.details.append(_format_inconsistency_message("variable name", node.id, self.file_path, node.lineno, "snake_case"))

        visitor = ConsistencyVisitor(file_path)
        visitor.visit(tree)
        total_names += visitor.total_names
        inconsistent_names += visitor.inconsistent_names
        details.extend(visitor.details)

    if total_names == 0:
        return 10.0, ["No relevant names found to check."]

    consistency_ratio = (total_names - inconsistent_names) / total_names
    consistency_score = consistency_ratio * 10.0
    details.insert(0, f"Naming consistency: {consistency_ratio*100:.2f}% ({total_names - inconsistent_names}/{total_names} consistent)")

    return min(10.0, max(0.0, consistency_score)), details