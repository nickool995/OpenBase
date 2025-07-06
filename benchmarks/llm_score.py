"""LLM-driven qualitative code assessment using Gemini Pro 2.5.

This benchmark sends a condensed summary of the codebase to Gemini and
requests a 0–10 quality score. It requires the env var `GEMINI_API_KEY`.
Because token limits make it impossible to send every file, we sample:
 • all README / docs files
 • first 300 lines of the 5 largest .py files
Feel free to tweak the sampling logic.
"""

from pathlib import Path
import os
from typing import List, Tuple
import textwrap

from .utils import get_python_files
from dotenv import load_dotenv
load_dotenv()

try:
    import google.generativeai as genai  # type: ignore
except ImportError:  # library optional
    genai = None  # type: ignore


MAX_CHARS = 16_000  # keep prompt under safety limit


def _sample_code(codebase_path: str) -> str:
    path = Path(codebase_path)
    snippets: List[str] = []

    # Include README-like files
    for readme_name in ("README.md", "readme.md", "README.rst"):
        readme_path = path / readme_name
        if readme_path.exists():
            snippets.append(f"# {readme_name}\n" + readme_path.read_text(encoding="utf-8")[:2000])

    # Take 5 largest .py files
    py_files = get_python_files(codebase_path)
    py_files.sort(key=lambda p: os.path.getsize(p), reverse=True)
    for fp in py_files[:5]:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            code = "\n".join(f.readlines()[:300])  # first 300 lines
        snippets.append(f"# {fp}\n" + code)

    joined = "\n\n".join(snippets)
    return joined[:MAX_CHARS]


PROMPT_TEMPLATE = textwrap.dedent(
    """
    You are an expert software architect reviewing a codebase.
    Provide a single integer 0-10 (10 = enterprise-grade, 0 = awful)
    representing overall code quality. Consider readability, maintainability,
    testing, security, documentation, and scalability based *only* on the
    snippet provided. After the score add a short one-sentence justification.

    Respond **exactly** in the format: `SCORE: <int> - <justification>`.
    """
)


def assess_llm(codebase_path: str) -> Tuple[float, List[str]]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        return 0.0, [
            "Gemini not configured (set GEMINI_API_KEY and install google-generativeai).",
            "Skipping LLM score.",
        ]

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    snippet = _sample_code(codebase_path)
    prompt = PROMPT_TEMPLATE + "\n\n" + snippet

    try:
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0.0},
            safety_settings={},
        )
        text = resp.text.strip()
        if text.lower().startswith("score"):
            parts = text.split(" ")
            score_str = parts[1] if len(parts) > 1 else "0"
            score = float(score_str)
            justification = " ".join(parts[3:]) if len(parts) > 3 else ""
            return min(10.0, max(0.0, score)), [justification or text]
        else:
            return 0.0, ["Unexpected LLM response", text]
    except Exception as exc:  # pylint: disable=broad-except
        return 0.0, [f"LLM call failed: {exc}"]

# alias for dynamic loader (module name llm_score -> assess_llm_score)
assess_llm_score = assess_llm 