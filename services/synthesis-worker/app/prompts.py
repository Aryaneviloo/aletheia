"""
synthesis_worker.app.prompts
==============================

Centralized, versioned prompt templates for synthesis and self-correction.

Why centralized
----------------
In the original codebase, prompts were inline strings inside the task
function — impossible to version, A/B test, or improve without touching
pipeline logic. Every prompt here is a named constant with a clear
description of its purpose and expected variables.

All prompts use .format(**kwargs) — simple, no extra dependencies.
"""

from __future__ import annotations

# --- System prompt ---------------------------------------------------------

SYNTHESIS_SYSTEM_PROMPT = """You are Aletheia, a precise and honest research assistant.
Your answers are always grounded in the provided context.
If the context does not contain enough information to answer the question,
say so explicitly rather than speculating.
Never fabricate facts, citations, or details not present in the context."""

# --- Main synthesis prompt --------------------------------------------------

SYNTHESIS_PROMPT = """Answer the following question using ONLY the information
provided in the context below. Do not use any prior knowledge.

QUESTION:
{query}

CONTEXT:
{context}

Provide a clear, concise answer. If the context is insufficient, say:
"The provided context does not contain enough information to answer this question."
"""

# --- Self-correction prompt (used when judge score is low) -----------------

SELF_CORRECTION_PROMPT = """Your previous answer was flagged as potentially
unfaithful to the source context. Review the context and your answer carefully,
then provide a corrected, strictly grounded response.

ORIGINAL QUESTION:
{query}

CONTEXT:
{context}

YOUR PREVIOUS ANSWER:
{previous_answer}

FAITHFULNESS ISSUES IDENTIFIED:
{issues}

Please provide a corrected answer that is strictly grounded in the context above.
"""

# --- Judge prompt (used by judge-worker) ------------------------------------

JUDGE_PROMPT = """You are a faithfulness evaluator. Your job is to check whether
an answer is fully supported by the provided context.

QUESTION:
{query}

CONTEXT:
{context}

ANSWER TO EVALUATE:
{answer}

Evaluate the answer and respond with a JSON object in exactly this format:
{{
  "score": <float between 0.0 and 1.0>,
  "faithful": <true or false>,
  "issues": "<empty string if faithful, otherwise describe what claims are not supported by the context>"
}}

Score guide:
  1.0 = perfectly faithful, every claim is supported by the context
  0.7-0.9 = mostly faithful, minor unsupported details
  0.4-0.6 = partially faithful, some unsupported claims
  0.0-0.3 = largely unfaithful, major unsupported claims

Respond with ONLY the JSON object, no other text."""