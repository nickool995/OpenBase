"""Statistical utilities for benchmark normalization and confidence intervals."""

import numpy as np
from scipy import stats
from typing import List, Tuple, Dict, Any, Iterator, Optional
from .utils import get_python_files

def get_codebase_size_bucket(codebase_path: str) -> str:
    """
    Categorize a codebase by total lines of Python code.

    The function walks the list of Python file paths returned by get_python_files,
    counts non-empty lines in each file, and returns one of "small", "medium", or
    "large" according to the aggregated lines of code.

    Examples:
        >>> # Suppose get_python_files returns two files with 10 and 50 non-empty lines
        >>> # A test harness can monkeypatch get_python_files to simulate that behavior.
        >>> # The function returns "small" for total_loc < 100.
        >>> # get_codebase_size_bucket('/path/to/codebase')
        'small'

    Args:
        codebase_path: Path to the root of the codebase to analyze.

    Returns:
        A string bucket: "small", "medium", or "large".
    """
    python_files = get_python_files(codebase_path)
    total_loc = 0

    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                total_loc += sum(1 for line in f if line.strip())
        except (UnicodeDecodeError, IOError):
            continue

    if total_loc < 100:
        return "small"
    elif total_loc < 1000:
        return "medium"
    else:
        return "large"


def normalize_scores_zscore(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Lightly normalize a mapping of named scores to reduce the impact of extreme outliers.

    This function preserves the ordering and relationships between scores while compressing
    values above a threshold (10.0) if an extreme maximum is observed (> 15.0).

    Examples:
        >>> scores = {'a': 5.0, 'b': 20.0}
        >>> normalize_scores_zscore(scores)  # compress 'b' while preserving 'a'
        {'a': 5.0, 'b': 13.0}

    Args:
        scores: Mapping from identifier to numeric score.

    Returns:
        A new mapping with normalized score values. If the input has fewer than two
        entries, the original mapping is returned unchanged.
    """
    if len(scores) < 2:
        return scores

    values = list(scores.values())
    max_score = max(values)

    # If max score is very high compared to others, apply light scaling
    if max_score > 15.0:  # Only normalize if we have extreme outliers
        normalized: Dict[str, float] = {}
        for name, score in scores.items():
            # Scale down extreme scores but preserve relative relationships
            if score > 10.0:
                normalized[name] = 10.0 + (score - 10.0) * 0.3  # Compress scores above 10
            else:
                normalized[name] = score
        return normalized
    else:
        # No normalization needed - return original scores
        return scores


def calculate_confidence_interval(
    scores: List[float],
    confidence: float = 0.95
) -> Tuple[float, float]:
    """
    Calculate a Student-t confidence interval for a list of sample scores.

    Examples:
        >>> calculate_confidence_interval([1.0, 2.0])  # simple example with two samples
        (1.0, 2.0)  # exact output may vary depending on statistical rounding

    Args:
        scores: A list of numeric sample observations.
        confidence: Desired confidence level (default 0.95).

    Returns:
        A tuple (lower_bound, upper_bound). If fewer than two samples are provided,
        (0.0, 0.0) is returned to indicate an undefined interval.
    """
    if len(scores) < 2:
        return (0.0, 0.0)

    mean_score = np.mean(scores)
    sem = stats.sem(scores)  # standard error of mean
    interval = stats.t.interval(confidence, len(scores) - 1, loc=mean_score, scale=sem)

    return interval


def adjust_score_for_size(raw_score: float, bucket: str, metric_type: str) -> float:
    """
    Adjust a raw metric score based on codebase size to reduce bias.

    The adjustment multipliers are heuristic and intended to slightly favor small
    codebases for certain metrics and slightly penalize large ones where complexity
    is expected. The result is clamped to a maximum of 10.0.

    Examples:
        >>> adjust_score_for_size(8.0, 'small', 'maintainability')
        10.0  # (8.0 * 1.5 = 12.0, clamped to 10.0)

    Args:
        raw_score: The original metric score (typically on a 0-10 scale).
        bucket: One of "small", "medium", or "large".
        metric_type: The type of metric (e.g., "maintainability", "readability").

    Returns:
        The adjusted score, clamped to a maximum of 10.0.
    """
    adjustments = {
        "maintainability": {
            "small": 1.5,    # Small codebases get bonus (MI often artificially low)
            "medium": 1.0,   # No adjustment
            "large": 0.9     # Large codebases slightly penalized (complexity expected)
        },
        "readability": {
            "small": 1.2,
            "medium": 1.0,
            "large": 0.95
        },
        "default": {
            "small": 1.1,
            "medium": 1.0,
            "large": 1.0
        }
    }

    multiplier = adjustments.get(metric_type, adjustments["default"]).get(bucket, 1.0)
    return min(10.0, raw_score * multiplier)


class BenchmarkResult:
    """Enhanced result container with confidence intervals and metadata.

    This lightweight container holds a numeric score, human-readable details,
    optional raw metrics, and an optional confidence interval. It remains small
    and serializable-friendly for use in reporting pipelines.

    Examples:
        >>> br = BenchmarkResult(7.5, ['checked', 'passed'], {'mi': 75}, (7.0, 8.0))
        >>> br.score
        7.5
        >>> list(br)  # supports tuple-like unpacking
        [7.5, ['checked', 'passed']]
        >>> br.format_score_with_ci()
        '7.50 ±0.5'
    """

    def __init__(
        self,
        score: float,
        details: List[str],
        raw_metrics: Optional[Dict[str, Any]] = None,
        confidence_interval: Optional[Tuple[float, float]] = None
    ) -> None:
        """Initialize a new BenchmarkResult instance."""
        self.score: float = score
        self.details: List[str] = details
        self.raw_metrics: Dict[str, Any] = raw_metrics or {}
        self.confidence_interval: Tuple[float, float] = confidence_interval or (score, score)

    def __iter__(self) -> Iterator[Any]:
        """Maintain backward compatibility with tuple unpacking.

        Returns an iterator yielding score then details to allow:
            score, details = BenchmarkResult(...)
        """
        return iter([self.score, self.details])

    def format_score_with_ci(self) -> str:
        """Format score with confidence interval.

        Returns a short human-readable string. When the confidence interval is a
        point (no uncertainty), only the formatted score is returned. Otherwise,
        the output uses a "±" style half-range notation.

        Examples:
            >>> BenchmarkResult(7.5, []).format_score_with_ci()
            '7.50'
            >>> BenchmarkResult(7.5, [], confidence_interval=(7.0, 8.0)).format_score_with_ci()
            '7.50 ±0.5'

        Returns:
            A formatted string representation of the score and its uncertainty.
        """
        if self.confidence_interval[0] == self.confidence_interval[1]:
            return f"{self.score:.2f}"

        ci_range = self.confidence_interval[1] - self.confidence_interval[0]
        # Use list accumulation + join to avoid repeated small string allocations.
        parts = [f"{self.score:.2f}", " ±", f"{ci_range/2:.1f}"]
        return "".join(parts)