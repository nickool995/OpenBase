import os
import ast
import pathlib
from typing import Iterator, List, Optional

def get_python_files(path: str) -> List[str]:
    """
    Return a list of file system paths (as strings) to all Python files found under the given path.

    This function converts a lazily-evaluated iterator into a concrete list before returning to
    preserve the original behavior (list of strings). For very large codebases or filesystem
    trees (tens or hundreds of thousands of files), building this list may consume significant
    memory. In those cases, prefer get_python_files_iter which yields file paths lazily.

    Args:
        path: Root filesystem path (directory or file) to search for .py files.

    Returns:
        A list of file paths (strings) for every file matching the pattern '**/*.py'
        under the provided path.
    """
    path_obj = pathlib.Path(path)
    files_iter = (str(file) for file in path_obj.rglob('*.py'))
    # Explicit conversion point: callers receive a list. If callers need streaming behavior,
    # use get_python_files_iter to avoid large memory allocations.
    return list(files_iter)

def get_python_files_iter(path: str) -> Iterator[str]:
    """
    Lazily yield file system paths (as strings) to Python files found under the given path.

    This generator yields results as they are discovered and does not accumulate them in memory.
    Use this when processing very large directories to avoid high memory usage.

    Args:
        path: Root filesystem path (directory or file) to search for .py files.

    Yields:
        File paths (strings) for every file matching the pattern '**/*.py' under the provided path.
    """
    path_obj = pathlib.Path(path)
    for file in path_obj.rglob('*.py'):
        yield str(file)

def parse_file(file_path: str) -> Optional[ast.AST]:
    """
    Parse the Python source file at the given path into an AST.

    This utility reads the file using UTF-8 encoding and attempts to parse it into an ast.AST
    object. If the file cannot be decoded as UTF-8 or contains invalid Python syntax, None is
    returned to indicate parse failure.

    Args:
        file_path: Path to the Python source file to parse.

    Returns:
        The parsed ast.AST object on success, or None if parsing fails due to SyntaxError or
        UnicodeDecodeError.
    """
    with open(file_path, "r", encoding="utf-8") as source:
        try:
            return ast.parse(source.read(), filename=file_path)
        except (SyntaxError, UnicodeDecodeError):
            return None