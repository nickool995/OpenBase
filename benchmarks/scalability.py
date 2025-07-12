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

    for file_path in python_files:
        tree = parse_file(file_path)
        if not tree:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "asyncio" in alias.name: uses_asyncio = True
                    if "async" in alias.name: uses_asyncio = True
                    if "multiprocessing" in alias.name: uses_multiprocessing = True
                    if any(keyword in alias.name for keyword in caching_keywords): uses_caching_libs = True
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    if "asyncio" in node.module: uses_asyncio = True
                    if "async" in node.module: uses_asyncio = True
                    if "multiprocessing" in node.module: uses_multiprocessing = True
                    if any(keyword in node.module for keyword in caching_keywords): uses_caching_libs = True

            if isinstance(node, ast.FunctionDef):
                total_functions += 1
            elif isinstance(node, ast.AsyncFunctionDef):
                total_functions += 1
                async_functions += 1

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