"""
judge_worker.app.scoring
--------------------------

Parses and validates the LLm's faithfulness evalutation response

The judge LLM is prompted via JUGDE_PROMPT in synthesis-worker/prompts
to return a JSON object with score, faithful, and issues fields
"""

from __future__ import annotations
import json

import re
from dataclasses import dataclass

@dataclass
class JudgeScore:
    """
    Structured result of a faithfulness evaluation
    
    score: 0.0-1.0, the higher is it, more faithful to context
    If the value is 0.7 or higher it is faithful
    issues: empty string if faithful or else issues
    raw_response: LLM's full response used for debugging
    """
    score: float
    faithful: bool
    issues: str
    raw_response: str

FAITHFULNESS_SCORE = 0.7

def parse_judge_response(raw_response: str) -> JudgeScore:
    """
    Parse the LLm's JOSN into a judge score
    Uses three strats:
    Parse the whole response as jSON directly
    Extract the first block with regex
    Fall bak to a neutal score so one doesnt crash the pipeline
    """

    text = raw_response.strip()

    data = None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        pass


    if data is None:
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match: 
            try: 
                data = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if data is None:
        return JudgeScore(
            score=0.5,
            faithful=False,
            issues="Could not parse judge responses, defaulting to neutral score",
            raw_response=raw_response,
            )

    score = float(data.get("score", 0.5))
    score = max(0.0, min(1.0, score))
    faithful = bool(data.get("faithful", score >= FAITHFULNESS_SCORE))
    issues = str(data.get("issues", ""))

    return JudgeScore(
        score=score,
        faithful=faithful,
        issues=issues,
        raw_response=raw_response,
    )

