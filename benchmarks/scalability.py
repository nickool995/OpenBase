
import ast
from .utils import get_python_files, parse_file

def assess_scalability(codebase_path: str):
    """
    Assesses scalability by checking for use of asyncio, multiprocessing, and caching.
    This is a simplified static analysis.
    """
    python_files = get_python_files(codebase_path)
    if not python_files:
        return 0.0, ["No Python files found."]

    uses_asyncio = False
    uses_multiprocessing = False
    uses_caching_libs = False
    async_functions = 0
    total_functions = 0
    details = []
    
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
