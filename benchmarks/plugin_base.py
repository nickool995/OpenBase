from abc import ABC, abstractmethod
from typing import Tuple, List

class BenchmarkPlugin(ABC):
    """Base class for all benchmark plug-ins."""

    name: str = "Unnamed"

    @abstractmethod
    def run(self, codebase_path: str) -> Tuple[float, List[str]]:
        """Return (score, details).""" 