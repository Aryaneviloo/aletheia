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

import httpx
from celery.utils.log import get_task_logger


from aletheia_core.config import get_settings
from aletheia_core.db.base import session_scope
from aletheia_core.db.models import Job
from aletheia_core.queue.celery_app import Queues, celery_app
from app.scoring import FAITHFULNESS_SCORE, JudgeScore, parse_judge_response


JUDGE_PROMPT = """You are a faithfulness evaluator. Check whether the answer
is fully supported by the provided context.

QUESTION: {query}

CONTEXT: {context}

ANSWER: {answer}

Respond with ONLY a JSON object:
{{"score": <0.0-1.0>, "faithful": <true/false>, "issues": "<empty or description>"}}

1.0 = perfectly faithful. 0.0 = completely unfaithful."""


log = get_task_logger(__name__)


def _call_judge_llm(query: str, context: str, answer: str) -> str:
    """Call inference-service ?generate with judge prompt"""

    settings = get_settings()
    prompt = JUDGE_PROMPT.format(query=query, context = context, answer=answer)
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

) -> dict:
    """
    Evaluate faithfulness of a synthesized answer
    
    job_id here is the SYNTHESIS job id
    """
    log.info(f"Judging answer for synthesis job{job_id}")

    try: 
        raw = _call_judge_llm(query, context, answer)
        score: JudgeScore = parse_judge_response(raw)

        log.info(
            f"Judge Score: {score.score:.2f} faithful ={score.faithful}"
            f" issues={score.issues or 'none'}"
        )


        #Update the syntehsis job with the judge result
        with session_scope() as db:
            job = db.get(Job, __import__('uuid').UUID(job_id))
            if job and job.result:
                job.result = {
                    **job.result,
                    "judge_score": score.score,
                    "judge_faithful": score.faithful,
                    "judge_issues": score.issues,
                }

                #self correction

        if not score.faithful:
            log.warning(
                f"Answer not faithful (score = {score.score:.2f}),"
                f"dispatching self correction"
            )
            celery_app.send_task(
                "synthesis.process_synthesis",
                kwargs={
                    "job_id": job_id,
                    "user_id": _get_user_id_for_job(job_id),
                    "query": query,
                    "collection_ids": [],   # strategist will use all user collections
                },
                queue=Queues.SYNTHESIS,   # explicit — fixes bug #3
            )

        return {
            "job_id": job_id,
            "score": score.score,
            "faithful": score.faithful,
            "issues": score.issues,
        }

    except httpx.HTTPError as e:
        log.warning(f"Judge LLm call failed, retrying {e}")
        raise self.retry(exc = e)
    except Exception as exc:
        log.error(f"Judge failed for job {job_id}: {exc}")
        raise


def _get_user_id_for_job(job_id: str) -> str:
    """Look for user_id for a job needed for self correction dispatch"""
    import uuid
    with session_scope() as db:
        job = db.get(Job, uuid.UUID(job_id))
        return str(job.user_id) if job else ""