import hashlib
import json

import jwt


REVIEW_PLAN_BINDING_SCHEMA = 'sdoc-review-plan-binding/v1'


def review_plan_digest(value):
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def encode_review_plan_binding(
        secret_key, prompt, document_context, plan,
        review_task_id, generation_attempt_id):
    """Bind a progressive plan to one durable task attempt.

    This is an integrity binding, not an authentication credential. Endpoint
    authentication remains short-lived; no fixed expiry is included here so a
    healthy long-running review does not fail solely because it takes time.
    """
    payload = {
        'purpose': 'sdoc_review_plan',
        'schema_version': REVIEW_PLAN_BINDING_SCHEMA,
        'review_task_id': review_task_id,
        'generation_attempt_id': generation_attempt_id,
        'prompt_digest': review_plan_digest(prompt),
        'context_digest': review_plan_digest(document_context),
        'brief_digest': review_plan_digest(plan.get('brief')),
        'chunks_digest': review_plan_digest(plan.get('chunks')),
    }
    return jwt.encode(payload, secret_key, algorithm='HS256')


def review_plan_binding_matches(
        token, secret_key, prompt, document_context, brief, chunks,
        review_task_id, generation_attempt_id):
    try:
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
    except jwt.InvalidTokenError:
        return False
    return (
        payload.get('purpose') == 'sdoc_review_plan'
        and payload.get('schema_version') == REVIEW_PLAN_BINDING_SCHEMA
        and payload.get('review_task_id') == review_task_id
        and payload.get('generation_attempt_id') == generation_attempt_id
        and payload.get('prompt_digest') == review_plan_digest(prompt)
        and payload.get('context_digest') == review_plan_digest(document_context)
        and payload.get('brief_digest') == review_plan_digest(brief)
        and payload.get('chunks_digest') == review_plan_digest(chunks)
    )
