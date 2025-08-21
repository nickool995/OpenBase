from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
from typing import List

from git import Repo, InvalidGitRepositoryError

from .utils import get_python_files

THRESHOLD_DAYS = 180  # 6 months


# Primary entry point expected by dynamic loader
def assess_git_health(codebase_path: str) -> tuple[float, List[str]]:
    """Assess git-based code health: churn, age, hotspot identification.

    Pipeline:
    - Open the git repository rooted at the provided codebase_path (searches parents).
    - Collect commits within the last THRESHOLD_DAYS.
    - For each commit, count author contributions and record changed Python files
      whose paths start with the provided codebase_path.
    - Compute file churn statistics and a simple bus-factor metric.
    - Produce a numeric score in range [0, 10] and a list of human-readable details.

    Assumptions and notes:
    - codebase_path is treated as a path prefix for file paths reported by git.
    - Only .py files are considered for churn/hotspot analysis.
    - The function returns early with a high score and explanatory message if the
      provided path is not a git repository or if churn is very low.
    - Memory: commits are materialized as a list from the git iterator because the
      library returns a generator; per-commit file listings are streamed via a
      generator expression to avoid creating large intermediate lists.
    """
    try:
        repo = Repo(Path(codebase_path).resolve(), search_parent_directories=True)
    except InvalidGitRepositoryError:
        return 5.0, ["Not a git repository; skipping git health checks."]

    now = datetime.utcnow()

    # Collect commits in the recent window
    since_date = now - timedelta(days=THRESHOLD_DAYS)
    commits = list(repo.iter_commits(paths=codebase_path, since=since_date.isoformat()))

    file_counter: Counter[str] = Counter()
    author_counter: Counter[str] = Counter()
    all_qualifying = []

    # Iterate commits and update counters.
    # Use a generator expression for per-commit file filtering to avoid building
    # large intermediate lists when commits touch many files.
    for commit in commits:
        # Count commits per author
        author_counter[commit.author.email] += 1

        qualifying_files = (
            f for f in commit.stats.files.keys()
            if f.endswith(".py") and f.startswith(codebase_path)
        )
        # extend accepts any iterable; the generator will be consumed here.
        all_qualifying.extend(qualifying_files)

    file_counter = Counter(all_qualifying)

    details: List[str] = []

    if not file_counter:
        return 8.0, ["Low churn detected in the last 6 months."]

    most_changed = file_counter.most_common(5)

    # Build the change messages as a list and extend details to avoid any
    # repeated string concatenation in loops.
    change_messages = [f"{f} changed {n} times in last 6 months." for f, n in most_changed]
    details.extend(change_messages)

    avg_churn = sum(file_counter.values()) / len(file_counter)
    # Insert summary at the front
    details.insert(0, f"Average churn / file: {avg_churn:.1f} commits in last 6 months.")

    bus_factor = len(author_counter)
    details.append(f"Bus factor (unique committers): {bus_factor}")

    # Scoring: moderate churn is ok; very high churn => lower score
    if avg_churn < 3:
        score = 9.0
    elif avg_churn < 10:
        score = 7.0
    elif avg_churn < 20:
        score = 5.0
    else:
        score = 3.0

    # Reward higher bus factor (more contributors)
    score += min(2.0, bus_factor / 5.0)

    return min(10.0, score), details

# Backward compatibility alias
assess_githealth = assess_git_health