from sqlalchemy import desc
from datetime import datetime, timedelta
from seafile_ai.chat_manager.utils import (
    combine_attachments_to_message,
    retrieve_origin_reference_format,
    strip_content_details_from_attachments,
)


class OpenAIMemory:
    def __init__(self, system_prompts):
        if isinstance(system_prompts, str):
            system_prompts = [{
                'role': 'system',
                'content': system_prompts,
            }]
        self.system_prompts = [dict(prompt) for prompt in system_prompts]
        self.reset_steps()

    def reset_steps(self):
        self.steps = [dict(prompt) for prompt in self.system_prompts]

    def append(self, step):
        self += step

    @property
    def context_thought_process(self):
        results = []

        for step in self.steps[1:]:
            if 'created_at' not in step:
                continue

            date = step['created_at']
            if step['role'] == 'assistant':
                assistant_response = {
                    'date': date,
                    'content': {
                        'answer': step.get('content') or '',
                        'sources': step.get('sources') or [],
                    },
                }
                if not results:
                    results.append({
                        'date': date,
                        'assistant_response': [assistant_response],
                    })
                else:
                    results[-1]['assistant_response'].append(assistant_response)
                continue

            results.append({
                'date': date,
                'user_input': {
                    'attachments': strip_content_details_from_attachments(step.get('attachments') or []),
                    'message': step.get('content') or '',
                },
                'assistant_response': [],
            })

        return results

    def __add__(self, steps):
        if isinstance(steps, dict):
            self.steps.append(steps)
        elif isinstance(steps, list):
            for step in steps:
                self += step
        else:
            raise TypeError('steps only receive two types: dict or list')
        return self

    def __iter__(self):
        for step in self.steps:
            if 'created_at' not in step:
                yield step
                continue

            if step['role'] == 'assistant':
                yield {
                    'role': 'assistant',
                    'content': retrieve_origin_reference_format(
                        step.get('content') or '',
                        step.get('sources') or [],
                    ),
                }
                continue

            yield {
                'role': 'user',
                'content': combine_attachments_to_message(
                    step.get('attachments') or [],
                    step.get('content') or '',
                ),
            }


def build_memory_from_db(db_session_class, system_prompts, session_uuid, window_limit, valid_time, message_model):
    memory = OpenAIMemory(system_prompts)
    if not session_uuid:
        return memory

    assert isinstance(window_limit, int), 'Invalid window number of context'
    assert isinstance(valid_time, int), 'Invalid valid time of context'

    with db_session_class() as db_session:
        query_args = [
            message_model.session_uuid == session_uuid,
            message_model.role.in_(['user', 'assistant'])
        ]
        if valid_time > 0:
            query_args.append(
                message_model.created_at > datetime.now() - timedelta(hours=valid_time)
            )
        records = (
            db_session.query(message_model)
            .filter(*query_args)
            .order_by(desc(message_model.created_at))
        )

        if window_limit > 0:
            records = records.limit(window_limit)

        records = records.all()

        records.sort(key=lambda x: x.created_at)
        
        for record in records:
            memory += record.to_dict()

    return memory
