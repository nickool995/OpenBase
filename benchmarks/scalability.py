import ast
from typing import List, Tuple
from .utils import get_python_files, parse_file

def assess_scalability(codebase_path: str) -> Tuple[float, List[str]]:
    """
    Perform a lightweight static assessment of a Python codebase's scalability characteristics.

    The function scans Python files under `codebase_path` (using get_python_files and parse_file)
    and looks for:
      - use of asyncio or async keywords (I/O-bound concurrency),
      - use of multiprocessing (CPU-bound parallelism),
      - references to common caching/task-queue libraries (e.g., redis, celery).

    It returns a tuple of (score, details) where `score` is a float in [0.0, 10.0] representing
    an approximate capability to scale (higher is better), and `details` is a list of human-readable
    observations discovered during the scan.

    Scalability and blocking I/O considerations:
    - This implementation relies on get_python_files and parse_file which are synchronous and may
      perform filesystem I/O. For very large repositories, calling these synchronously can be slow.
      Possible improvements (outside the scope of this function to preserve behavior) include:
        * Batching or streaming file discovery and parsing (yielding results incrementally).
        * Running parse operations concurrently (e.g., with threads or processes) if parse_file
          itself is CPU-bound or blocking.
        * Converting file I/O to async equivalents when integrating with an async runtime.
    - The returned analysis is static and heuristic-based; it does not execute project code and thus
      cannot detect runtime configuration or dynamically loaded libraries.

    Note: The function preserves deterministic behavior and returns a list of detail strings so
    callers can display, log, or further process individual observations.
    """
    python_files = get_python_files(codebase_path)
    if not python_files:
        return 0.0, ["No Python files found."]

    uses_asyncio = False
    uses_multiprocessing = False
    uses_caching_libs = False
    async_functions = 0
    total_functions = 0
    details: List[str] = []
    
    caching_keywords = ["redis", "memcached", "celery", "cache", "cachetools", "cachetools.cached"]

    class ScalabilityVisitor(ast.NodeVisitor):
        def __init__(self):
            self.uses_asyncio = False
            self.uses_multiprocessing = False
            self.uses_caching_libs = False
            self.async_functions = 0
            self.total_functions = 0

        def visit_Import(self, node):
            for alias in node.names:
                if "asyncio" in alias.name or "async" in alias.name:
                    self.uses_asyncio = True
                if "multiprocessing" in alias.name:
                    self.uses_multiprocessing = True
                if any(keyword in alias.name for keyword in caching_keywords):
                    self.uses_caching_libs = True
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            if node.module:
                if "asyncio" in node.module or "async" in node.module:
                    self.uses_asyncio = True
                if "multiprocessing" in node.module:
                    self.uses_multiprocessing = True
                if any(keyword in node.module for keyword in caching_keywords):
                    self.uses_caching_libs = True
            self.generic_visit(node)

        def visit_FunctionDef(self, node):
            self.total_functions += 1
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            self.total_functions += 1
            self.async_functions += 1
            self.generic_visit(node)

    for file_path in python_files:
        tree = parse_file(file_path)
        if tree:
            visitor = ScalabilityVisitor()
            visitor.visit(tree)
            uses_asyncio = uses_asyncio or visitor.uses_asyncio
            uses_multiprocessing = uses_multiprocessing or visitor.uses_multiprocessing
            uses_caching_libs = uses_caching_libs or visitor.uses_caching_libs
            total_functions += visitor.total_functions
            async_functions += visitor.async_functions

    score = 0
    if uses_asyncio:
        score += 3.0
        details.append("Uses 'asyncio' for I/O-bound concurrency.")
    if uses_multiprocessing:
        score += 3.0
        details.append("Uses 'multiprocessing' for CPU-bound parallelism.")
    if uses_caching_libs:
        score += 2.0
        details.append("Appears to use a caching or task queue library (e.g., Redis, Celery).")
    
    if total_functions > 0:
        async_ratio = async_functions / total_functions
        if async_ratio > 0:
            details.append(f"{async_ratio*100:.1f}% of functions are async.")
        score += async_ratio * 2.0
        
    return min(10.0, max(0.0, score)), details