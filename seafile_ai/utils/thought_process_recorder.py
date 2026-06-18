from seafile_ai.utils import object_to_json_str


class ThoughtProcessRecorder:
    def __init__(self):
        self.task = {}
        self.actions = []
        self.context = []
        self.final_answer = {}

    def set_task(self, system_prompts_messages, user_raw_input, user_message, attachments):
        self.task = {
            'system_prompts': [
                system_prompt_message['content']
                for system_prompt_message in system_prompts_messages
            ],
            'user_input': {
                'raw': user_raw_input,
                'message': user_message,
                'attachments': attachments,
            },
        }

    def add_tool_calls_group(self):
        self.actions.append({
            'tool_calls': [],
            'completion_retry': [],
            'tool_retry': [],
            'token_usage': {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
            },
            'time_usage': 0,
            'result': '',
        })

    def set_last_group_time_usage(self, time_usage):
        if self.actions:
            self.actions[-1]['time_usage'] = time_usage

    def update_last_group_tokens_usage(self, tokens_usage=None, replace=False):
        if not self.actions:
            return
        tokens_usage = tokens_usage or {}
        target = self.actions[-1]['token_usage']
        if replace:
            target['input_tokens'] = tokens_usage.get('input_tokens', 0)
            target['output_tokens'] = tokens_usage.get('output_tokens', 0)
            target['total_tokens'] = tokens_usage.get('total_tokens', 0)
            return
        target['input_tokens'] += tokens_usage.get('input_tokens', 0)
        target['output_tokens'] += tokens_usage.get('output_tokens', 0)
        target['total_tokens'] += tokens_usage.get('total_tokens', 0)

    def set_last_group_error(self, error):
        if self.actions:
            self.actions[-1]['error'] = {
                'type': error['type'],
                'message': error['message'],
            }

    def set_last_group_completion_retry(self, retries):
        if self.actions:
            self.actions[-1]['completion_retry'] = retries or []

    def append_last_group_tool_retry(self, errors):
        if self.actions and errors:
            self.actions[-1]['tool_retry'].extend(errors)

    def add_tool_call(self, tool_name, arguments, execution_detail, result=None):
        if not self.actions:
            return
        tool_call = {
            'name': tool_name,
            'arguments': {key: object_to_json_str(value) for key, value in arguments.items()},
        }
        self.actions[-1]['tool_calls'].append(tool_call)
        if execution_detail:
            self.actions[-1]['tool_calls'][-1]['execution_detail'] = execution_detail
        if result is not None:
            self.actions[-1]['result'] += object_to_json_str(result) + '\n'

    def set_final_answer(self, result, reach_max_steps=False, token_usage=None, time_usage=0, retry=None):
        self.final_answer = {
            'result': result,
            'reach_max_steps': reach_max_steps,
            'token_usage': token_usage or {},
            'time_usage': time_usage,
        }
        if retry:
            self.final_answer['retry'] = retry

    @property
    def details(self):
        return {
            'task': self.task,
            'context': self.context,
            'actions': self.actions,
            'final_answer': self.final_answer,
        }
