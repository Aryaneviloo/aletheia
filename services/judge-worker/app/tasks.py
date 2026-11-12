"""
judge_worker.app.tasks
----------------------

Faithfulness evaluation task

Flow:
 - call inference service/ generate with JUDGE_PROMPT
 - parse response into jUdgescore
 - update job with score + faithful flag
 - if not faithful: dispatch self correction task to synthesis queue
"""

from __future__ import annotations

import time
import uuid

import httpx
from celery.exceptions import Retry
from celery.utils.log import get_task_logger


from aletheia_core.config import get_settings
from aletheia_core.db.base import session_scope
from aletheia_core.db.models import Job
from aletheia_core.queue.celery_app import Queues, celery_app
from app.scoring import JudgeScore, parse_judge_response


JUDGE_PROMPT = """You are a faithfulness evaluator. Check whether the answer
is fully supported by the provided context.

QUESTION: {query}

CONTEXT: {context}

ANSWER: {answer}

Respond with ONLY a JSON object:
{{"score": <0.0-1.0>, "faithful": <true/false>, "issues": "<empty or description>"}}

1.0 = perfectly faithful. 0.0 = completely unfaithful."""


log = get_task_logger(__name__)


def _fill(template: str, **kwargs: str) -> str:
    """format() with braces in the answer escaped so they stay literal."""
    safe = {key: value.replace("{", "{{").replace("}", "}}") for key, value in kwargs.items()}
    return template.format(**safe)


def _call_judge_llm(query: str, context: str, answer: str) -> str:
    """Call inference-service /generate with judge prompt"""

    settings = get_settings()
    prompt = _fill(JUDGE_PROMPT, query=query, context=context, answer=answer)
    response = httpx.post(
        f"{settings.inference_service_url}/generate",
        json = {
            "prompt": prompt,
            "system_prompt": "You are a strict faithfulness evaluator. Respond only in JSON.",
            "max_tokens": 256,
            "temperature": 0.0
        },
        timeout=60.0,
    )

    response.raise_for_status()
    return response.json()["content"]

@celery_app.task(
    name="judge.evaluate_answer",
    bind=True,
    max_retries=2,
    default_retry_delay = 30,
    acks_late = True,
)

def evaluate_answer(
    self,
    job_id: str,
    query: str,
    context: str,
    answer: str,
    user_id: str = "",
    collection_ids: list[str] | None = None,
    dialogue_id: str | None = None,
    attempt: int = 0,
) -> dict:
    """
    Evaluate faithfulness of a synthesized answer.

    job_id here is the SYNTHESIS job id. A failing score schedules one
    correction on the same collections. That correction is not judged again.
    """
    log.info(f"Judging answer for synthesis job {job_id} attempt={attempt}")

    try:
        raw = _call_judge_llm(query, context, answer)
        score: JudgeScore = parse_judge_response(raw)

        log.info(
            f"Judge Score: {score.score:.2f} faithful={score.faithful}"
            f" issues={score.issues or 'none'}"
        )

        _attach_judge_score(job_id, score)

        if not score.faithful and attempt == 0:
            owner_id = user_id or _get_user_id_for_job(job_id)
            if not owner_id:
                log.error(f"Cannot self-correct job {job_id}: missing user_id")
            else:
                log.warning(
                    f"Answer not faithful (score={score.score:.2f}), dispatching one self-correction"
                )
                celery_app.send_task(
                    "synthesis.process_synthesis",
                    kwargs={
                        "job_id": job_id,
                        "user_id": owner_id,
                        "query": query,
                        "collection_ids": collection_ids or [],
                        "dialogue_id": dialogue_id,
                        "attempt": 1,
                        "previous_answer": answer,
                        "issues": score.issues,
                    },
                    queue=Queues.SYNTHESIS,
                )

        return {
            "job_id": job_id,
            "score": score.score,
            "faithful": score.faithful,
            "issues": score.issues,
        }

    except httpx.HTTPError as e:
        log.warning(f"Judge LLM call failed, retrying {e}")
        if self.request.retries < (self.max_retries or 0):
            raise self.retry(exc=e)
        raise
    except Retry:
        raise
    except Exception as exc:
        log.error(f"Judge failed for job {job_id}: {exc}")
        raise


def _attach_judge_score(job_id: str, score: JudgeScore, attempts: int = 5) -> None:
    """Merge the score onto the synthesis job once its result row exists."""
    job_uuid = uuid.UUID(job_id)
    for try_index in range(attempts):
        with session_scope() as db:
            job = db.get(Job, job_uuid)
            if job and job.result:
                job.result = {
                    **job.result,
                    "judge_score": score.score,
                    "judge_faithful": score.faithful,
                    "judge_issues": score.issues,
                }
                return
        if try_index < attempts - 1:
            time.sleep(0.5)
    log.warning(f"Job {job_id} had no result to attach the judge score to")


def _get_user_id_for_job(job_id: str) -> str:
    """Look for user_id for a job needed for self correction dispatch"""
    import uuid
    with session_scope() as db:
        job = db.get(Job, uuid.UUID(job_id))
        return str(job.user_id) if job else ""