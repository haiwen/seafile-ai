import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import litellm
from litellm.llms.custom_httpx.http_handler import HTTPHandler

from test_chat_memory import load_memory
from test_chat_title import load_chat_utils
from test_llm_tier_config import PROJECT_ROOT, load_llm_api, load_module


def load_chat():
    api = load_llm_api({}, {'model': 'gpt-5', 'type': 'openai'})
    config = SimpleNamespace(
        SEAFILE_SERVER_URL='https://seafile.example.com',
        SEASEARCH_URL='', SEASEARCH_TOKEN='', MAX_STEPS=3,
        COMPLETION_MAX_RETRIES=2, COMPLETION_RETRY_INTERVAL=0,
        TOOL_CALL_MAX_RETRIES=1, TOOL_CALL_RETRY_INTERVAL=0,
    )
    modules = {'seafile_ai': SimpleNamespace(config=config), 'seafile_ai.config': config}
    utils = load_module('test_responses_utils', PROJECT_ROOT / 'seafile_ai/utils/__init__.py', {
        **modules,
        **{name: Mock() for name in (
            'requests', 'mammoth', 'PIL', 'pdfminer.high_level', 'seafobj',
            'seafile_ai.utils.sdoc2md', 'seafile_ai.utils.parse_pptx',
        )},
    })
    modules['seafile_ai.utils'] = utils
    for name, path in (
            ('seafile_ai.utils.thought_process_recorder', 'seafile_ai/utils/thought_process_recorder.py'),
            ('seafile_ai.utils.tools', 'seafile_ai/utils/tools.py'),
            ('seafile_ai.utils.sse', 'seafile_ai/utils/sse.py'),
            ('seafile_ai.chat_manager.utils.chat_utils', 'seafile_ai/chat_manager/utils/chat_utils.py'),
            ('seafile_ai.chat_manager.utils.callbacker', 'seafile_ai/chat_manager/utils/callbacker.py'),
            ('seafile_ai.chat_manager.system_prompts', 'seafile_ai/chat_manager/system_prompts.py')):
        modules[name] = load_module(name, PROJECT_ROOT / path, modules)
    modules.update({
        'seafile_ai.db.models': SimpleNamespace(ChatMessages=object),
        'seafile_ai.chat_manager.memory': load_memory(),
        'seafile_ai.chat_manager.utils': load_chat_utils(Mock()),
        'seafile_ai.chat_manager.tools': SimpleNamespace(
            DocumentsSearch=object, ListFiles=object, ReadFiles=object, MarkdownGenerator=object,
        ),
        'seafile_ai.utils.llm_api': api,
    })
    chat_module = load_module('test_responses_chat', PROJECT_ROOT / 'seafile_ai/chat_manager/__init__.py', modules)
    return chat_module, api, modules['seafile_ai.utils.tools']


def completed(output):
    return {'type': 'response.completed', 'response': {
        'status': 'completed',
        'output': output,
        'usage': {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15},
    }}


def function_call(name, call_id, arguments='{}'):
    return {'type': 'function_call', 'id': 'fc_' + call_id, 'call_id': call_id, 'name': name, 'arguments': arguments}


class ChatResponsesTest(unittest.TestCase):
    def setUp(self):
        self.module, self.api, tools = load_chat()
        self.tools = tools
        self.litellm = self.api.responses.litellm
        self.data_logger = Mock()
        self.chat = self.module.StreamingChat(SimpleNamespace(data_logger=self.data_logger))
        self.executor = tools.OpenAIToolExecutor()
        self.context = {'repo_id': 'repo-id', 'scenario': 'chat'}
        self.final_output = [{
            'type': 'message', 'id': 'msg_final', 'role': 'assistant',
            'content': [{'type': 'output_text', 'text': 'Completed.'}],
        }]

    def run_chat(self):
        events = list(self.chat.run(None, self.executor, 'Read the plan.', [], context=self.context))
        self.assertEqual(events[-1], 'data: [DONE]\n\n')
        return [json.loads(event[len('data: '):]) for event in events[:-1]]

    def test_valid_arguments_are_checked_before_server_parameters_are_injected(self):
        app = SimpleNamespace()
        call_back = Mock()

        def scoped_tool(query, context, app, model, tool_executor, call_back):
            return query, context, app, model, tool_executor, call_back

        self.executor.register(scoped_tool, {
            'type': 'function', 'name': 'scoped_tool',
            'parameters': {
                'type': 'object', 'properties': {'query': {'type': 'string'}},
                'required': ['query'],
            },
        }, context=self.context, app=app, model='server-model')

        result = self.executor.execute(function_call(
            'scoped_tool', 'scope_1', '{"query": "plan"}',
        ), call_back)

        self.assertEqual(result, (
            'plan', self.context, app, 'server-model', self.executor, call_back,
        ))

    def test_model_arguments_cannot_supply_server_parameters(self):
        tool = Mock()
        self.executor.register(tool, {
            'type': 'function', 'name': 'scoped_tool',
            'parameters': {
                'type': 'object', 'properties': {'query': {'type': 'string'}},
                'required': ['query'],
            },
        }, context=self.context, app=SimpleNamespace(), model='server-model')

        for field in ('context', 'app', 'model', 'tool_executor', 'call_back'):
            with self.subTest(field=field):
                with self.assertRaisesRegex(self.tools.InvalidToolException, f'unexpected fields: {field}') as caught:
                    self.executor.execute(function_call(
                        'scoped_tool', 'scope_1', json.dumps({'query': 'plan', field: 'model-value'}),
                    ))
                self.assertEqual(caught.exception.unexpected_fields, [field])

        tool.assert_not_called()

    def test_rejects_missing_required_fields_and_invalid_values(self):
        tool = Mock()
        self.executor.register(tool, {
            'type': 'function', 'name': 'scoped_tool',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'file_paths': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1},
                },
                'required': ['query'],
            },
        })

        for arguments, message in (
                ({}, 'missing required fields: query'),
                ({'query': 42}, r'\$\.query:.*string'),
                ({'query': 'plan', 'file_paths': [42]}, r'\$\.file_paths\[0\]:.*string'),
                ({'query': 'plan', 'file_paths': []}, r'\$\.file_paths:')):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(self.tools.InvalidToolException, message):
                    self.executor.execute(function_call('scoped_tool', 'scope_1', json.dumps(arguments)))

        tool.assert_not_called()

    def test_invalid_arguments_return_tool_error_and_allow_corrected_call(self):
        for arguments, error_type in (
                ('{', 'JSONDecodeError'),
                ('{"file_path": "/plan.md", "context": {"repo_id": "model-repo"}}', 'InvalidToolArgumentsException'),
                ('{}', 'InvalidToolArgumentsException'),
                ('{"file_path": 42}', 'InvalidToolArgumentsException'),
                ('[]', 'InvalidToolException')):
            with self.subTest(arguments=arguments):
                self.executor = self.tools.OpenAIToolExecutor()
                read_plan = Mock(return_value='Plan content.')
                self.executor.register(read_plan, {
                    'type': 'function', 'name': 'read_plan',
                    'parameters': {
                        'type': 'object', 'properties': {'file_path': {'type': 'string'}},
                        'required': ['file_path'],
                    },
                })
                self.litellm.responses = Mock(side_effect=[
                    [completed([function_call('read_plan', 'invalid_1', arguments)])],
                    [completed([function_call('read_plan', 'corrected_1', '{"file_path": "/plan.md"}')])],
                    [completed(self.final_output)],
                ])

                with self.assertLogs(level='ERROR'):
                    events = self.run_chat()

                requests = [call.kwargs for call in self.litellm.responses.call_args_list]
                self.assertEqual(len(requests), 3)
                failure = next(item for item in requests[1]['input'] if item.get('type') == 'function_call_output')
                self.assertEqual(failure['call_id'], 'invalid_1')
                self.assertIn(error_type, failure['output'])
                read_plan.assert_called_once_with(file_path='/plan.md')
                success = next(item for item in requests[2]['input'] if item.get('type') == 'function_call_output' and item.get('call_id') == 'corrected_1')
                self.assertEqual(json.loads(success['output']), 'Plan content.')
                result = events[-1]['results']
                self.assertEqual(result['answer'], 'Completed.')
                action = result['thought_process']['actions'][0]
                self.assertIsInstance(action['tool_calls'][0]['arguments'], dict)
                self.assertEqual(len(action['tool_retry']), 2)
                self.assertTrue(all(error_type in error for error in action['tool_retry']))
                self.assertEqual(action['error']['type'], 'ToolRetryExceeded')

    def test_multistep_tools_keep_full_output_and_return_existing_sse(self):
        calls = []
        document = [{'path': '/plan.md', 'content': 'Full document content.'}]

        def list_files(context, call_back, tool_executor, include_dirs=False):
            calls.append((context, tool_executor, include_dirs))
            call_back('update_execution_detail', {'Files found': 1})
            return {'records': [{'path': '/plan.md'}]}

        read_files = Mock(return_value=document)
        failing_tool = Mock(side_effect=RuntimeError('tool unavailable'))
        for name, func, parameters in (
                ('list_files', list_files, {'type': 'object', 'properties': {'include_dirs': {'type': 'boolean'}}}),
                ('read_files', read_files, {'type': 'object', 'properties': {'file_paths': {'type': 'array'}}}),
                ('failing_tool', failing_tool, {'type': 'object'})):
            self.executor.register(func, {'type': 'function', 'name': name, 'parameters': parameters}, context=self.context)

        first_output = [
            {'type': 'reasoning', 'id': 'rs_1', 'summary': [], 'encrypted_content': 'encrypted-state'},
            {'type': 'message', 'id': 'msg_1', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Reading.'}]},
            function_call('list_files', 'list_1'),
            function_call('read_files', 'read_1', '{"file_paths": ["/plan.md"]}'),
        ]
        second_output = [function_call('failing_tool', 'fail_1')]
        self.litellm.responses = Mock(side_effect=[
            [completed(first_output)],
            [completed(second_output)],
            [{'type': 'response.output_text.delta', 'delta': 'Completed.'}, completed(self.final_output)],
        ])

        with self.assertLogs(level='ERROR'):
            events = self.run_chat()

        requests = [call.kwargs for call in self.litellm.responses.call_args_list]
        self.assertEqual(len(requests), 3)
        self.assertEqual(calls, [(self.context, self.executor, False)])
        read_files.assert_called_once_with(file_paths=['/plan.md'])
        self.assertEqual(failing_tool.call_count, 2)
        self.assertTrue(all(tool['strict'] is False and 'function' not in tool for tool in requests[0]['tools']))
        second_input = requests[1]['input']
        initial_length = len(requests[0]['input'])
        self.assertEqual(second_input[initial_length:initial_length + len(first_output)], first_output)
        outputs = [item for item in second_input if item.get('type') == 'function_call_output']
        self.assertEqual([item['call_id'] for item in outputs], ['list_1', 'read_1'])
        self.assertEqual(json.loads(outputs[1]['output']), document)
        self.assertEqual(document[0]['content'], 'Full document content.')
        failure = next(item for item in requests[2]['input'] if item.get('call_id') == 'fail_1' and item.get('type') == 'function_call_output')
        self.assertIn('tool unavailable', failure['output'])
        self.assertNotIn('tools', requests[2])
        self.assertEqual(requests[2]['tool_choice'], 'none')
        self.assertEqual(self.data_logger.log_data.call_count, 3)
        self.assertIn({'answer': 'Completed.'}, events)
        result = events[-1]['results']
        self.assertEqual(result['answer'], 'Completed.')
        self.assertEqual(result['sources'], [])
        thought_process = result['thought_process']
        self.assertEqual(len(thought_process['actions']), 2)
        self.assertEqual(len(thought_process['actions'][0]['tool_calls']), 2)
        self.assertNotIn('Full document content.', thought_process['actions'][0]['result'])
        self.assertEqual(thought_process['actions'][1]['error']['type'], 'ToolRetryExceeded')
        self.assertTrue(thought_process['final_answer']['reach_max_steps'])

    def test_completion_retries_keep_same_input_and_step(self):
        self.litellm.responses = Mock(side_effect=[
            RuntimeError('temporary failure'),
            [completed([])],
            [{'type': 'response.output_text.delta', 'delta': 'Completed.'}, completed(self.final_output)],
        ])

        with self.assertLogs(level='ERROR'):
            events = self.run_chat()

        requests = [call.kwargs for call in self.litellm.responses.call_args_list]
        self.assertEqual([request['input'] for request in requests], [requests[0]['input']] * 3)
        self.assertTrue(all('tools' in request for request in requests))
        result = events[-1]['results']['thought_process']['final_answer']
        self.assertEqual(result['result'], 'Completed.')
        self.assertFalse(result['reach_max_steps'])
        self.assertEqual([entry['reason'] for entry in result['retry']], ['completion_error', 'empty_visible_output'])
        self.assertEqual(self.data_logger.log_data.call_count, 2)

    def test_hosted_vllm_checks_response_status_through_real_litellm(self):
        self.api.responses.litellm = litellm
        self.api.DEFAULT_LLM_MODEL = {
            'type': 'other', 'model': 'gpt-4o-mini',
            'url': 'https://gateway.example/v1', 'key': 'test-key',
        }
        for status, error, incomplete_details, succeeds in (
                ('completed', None, None, True),
                ('incomplete', None, {'reason': 'max_output_tokens'}, False),
                ('failed', {'code': 'server_error', 'message': 'upstream failed'}, None, False),
                ('completed', {'code': 'server_error', 'message': 'upstream failed'}, None, False),
                ('completed', None, {'reason': 'max_output_tokens'}, False)):
            with self.subTest(status=status, error=error, incomplete_details=incomplete_details):
                self.executor = self.tools.OpenAIToolExecutor()
                self.data_logger.reset_mock()
                response = {
                    'id': 'resp_test', 'object': 'response', 'created_at': 1, 'model': 'gpt-4o-mini',
                    'status': status, 'error': error, 'incomplete_details': incomplete_details,
                    'output': [{
                        'type': 'message', 'id': 'msg_test', 'status': 'completed', 'role': 'assistant',
                        'content': [{'type': 'output_text', 'text': 'Response text.', 'annotations': []}],
                    }],
                }
                http_response = httpx.Response(
                    200, json=response,
                    request=httpx.Request('POST', 'https://gateway.example/v1/responses'),
                )
                with (
                    patch.object(HTTPHandler, 'post', return_value=http_response) as post,
                    patch.object(self.module.logger, 'exception') as log_error,
                ):
                    events = self.run_chat()

                post.assert_called_once()
                self.assertEqual(post.call_args.kwargs['url'], 'https://gateway.example/v1/responses')
                self.assertFalse(post.call_args.kwargs['stream'])
                self.assertTrue(any('answer' in event for event in events))
                if succeeds:
                    self.assertEqual(events[-1]['results']['answer'], 'Response text.')
                    log_error.assert_not_called()
                else:
                    self.assertIn('LLM or internal server error', events[-1]['results']['answer'])
                    self.data_logger.log_data.assert_not_called()
                    log_error.assert_called()
