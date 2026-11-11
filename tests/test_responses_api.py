import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from test_llm_tier_config import load_llm_api


class ResponsesAPITest(unittest.TestCase):
    def setUp(self):
        self.module = load_llm_api(
            {'low': {'model': 'small-model', 'type': 'openai'}},
            {'model': 'default-model', 'type': 'openai'},
            {'chat': {'model': 'gpt-5', 'type': 'openai', 'url': 'https://gateway.example/v1', 'key': 'test-key'}},
        )
        self.litellm = self.module.responses.litellm
        self.litellm.responses = Mock(return_value=[])
        self.litellm.completion = Mock()

    def test_chat_model_selection_and_responses_request(self):
        inputs = [{'role': 'user', 'content': 'Find a document.'}]
        tools = [{'type': 'function', 'name': 'list_files', 'parameters': {'type': 'object'}, 'strict': False}]
        client = self.module.get_responses_client_by_model_id(None, 'chat')
        client.responses_stream(input=inputs, tools=tools, context={'repo_id': 'repo-id'}, num_retries=1)

        request = self.litellm.responses.call_args.kwargs
        self.assertEqual(request, {
            'model': 'openai/gpt-5',
            'api_base': 'https://gateway.example/v1',
            'api_key': 'test-key',
            'timeout': 180,
            'store': False,
            'stream': True,
            'include': ['reasoning.encrypted_content'],
            'input': inputs,
            'tools': tools,
            'temperature': 1,
            'num_retries': 1,
        })
        self.litellm.completion.assert_not_called()
        for model_id in (None, 'missing'):
            with self.subTest(model_id=model_id):
                client = self.module.get_responses_client_by_model_id(None, model_id)
                self.assertIsInstance(client, self.module.ResponsesAPI)
                self.assertEqual(client.model_id, 'default-model')

    def test_provider_url_and_temperature(self):
        for provider in ('other', 'openai', 'anthropic'):
            with self.subTest(provider=provider):
                client = self.module.ResponsesAPI(None, 'claude-sonnet-4-5', provider, 'https://gateway.example/v1')
                client.responses_stream(input=[], temperature=0.1)
                request = self.litellm.responses.call_args.kwargs
                self.assertEqual(request['api_base'], 'https://gateway.example/v1')
                self.assertNotIn('base_url', request)
                self.assertNotIn('temperature', request)

    def test_ordinary_service_uses_completion_and_logs_usage(self):
        self.litellm.completion.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='summary'))],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        )
        data_logger = Mock()
        client = self.module.get_completion_client_by_model_tier(data_logger, 'low')

        self.assertEqual(client.run([{'role': 'user', 'content': 'Summarize.'}]), 'summary')
        self.assertIsInstance(client, self.module.CompletionAPI)
        self.assertEqual(client.last_token_usage, {'input_tokens': 2, 'output_tokens': 3})
        data_logger.log_data.assert_called_once()
        self.litellm.responses.assert_not_called()


class ResponsesParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = load_llm_api({}, {}).responses.ResponsesParser
        self.output = [
            {'type': 'reasoning', 'id': 'rs_1', 'summary': [], 'encrypted_content': 'encrypted-reasoning'},
            {'type': 'message', 'id': 'msg_1', 'role': 'assistant', 'content': [
                {'type': 'output_text', 'text': 'Find '}, {'type': 'output_text', 'text': 'files.'},
            ]},
            {'type': 'function_call', 'id': 'fc_1', 'call_id': 'call_1', 'name': 'list_files', 'arguments': '{}'},
            {'type': 'function_call', 'id': 'fc_2', 'call_id': 'call_2', 'name': 'read_files', 'arguments': '{"file_paths": ["/plan.md"]}'},
        ]
        self.response = {'status': 'completed', 'output': self.output, 'usage': {
            'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15,
            'input_tokens_details': {'cached_tokens': 2},
        }}

    def test_preserves_full_output_from_dict_and_sdk_object(self):
        sdk_response = Mock()
        sdk_response.model_dump.return_value = self.response
        for response in (self.response, sdk_response):
            with self.subTest(response_type=type(response).__name__):
                result = self.parser.parse_output(response)
                self.assertEqual(result.content, 'Find files.')
                self.assertEqual(result.tool_calls, self.output[2:])
                self.assertEqual(result.output, self.output)
                self.assertEqual(result.usage, {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15})
        sdk_response.model_dump.assert_called_once_with(exclude_none=True)

    def test_stream_uses_completed_output_and_text_deltas(self):
        completed = Mock()
        completed.model_dump.return_value = {'type': 'response.completed', 'response': self.response}
        events = [
            {'type': 'response.created'},
            {'type': 'response.output_text.delta', 'delta': 'Find '},
            {'type': 'response.output_text.delta', 'delta': 'files.'},
            {'type': 'response.output_item.done', 'item': self.output[2]},
            completed,
        ]
        results = list(self.parser.iter_stream(events))
        self.assertEqual(results[:2], [('text_delta', 'Find '), ('text_delta', 'files.')])
        self.assertEqual(results[2][0], 'completed')
        self.assertEqual(results[2][1].output, self.output)
        self.assertEqual(len(results[2][1].tool_calls), 2)

    def test_rejects_unsuccessful_responses(self):
        for status, error, incomplete_details, detail in (
                ('incomplete', None, {'reason': 'max_output_tokens'}, 'max_output_tokens'),
                ('failed', {'code': 'server_error', 'message': 'upstream failed'}, None, 'server_error'),
                ('in_progress', None, None, 'in_progress'),
                (None, None, None, 'status=None'),
                ('completed', {'code': 'server_error'}, None, 'server_error'),
                ('completed', None, {'reason': 'max_output_tokens'}, 'max_output_tokens'),
                ('completed', {}, None, 'error={}'),
                ('completed', None, {}, 'incomplete_details={}')):
            response = {
                **self.response,
                'status': status, 'error': error, 'incomplete_details': incomplete_details,
            }
            sdk_response = Mock()
            sdk_response.model_dump.return_value = response
            for payload in (response, sdk_response):
                with self.subTest(
                        status=status, error=error, incomplete_details=incomplete_details,
                        payload_type=type(payload).__name__):
                    with self.assertRaises(RuntimeError) as caught:
                        self.parser.parse_output(payload)
                    self.assertIn(detail, str(caught.exception))

    def test_failed_and_unfinished_streams_raise(self):
        for events in (
                [{'type': 'error', 'error': {'message': 'failed'}}],
                [{'type': 'response.failed', 'response': {'error': {'message': 'failed'}}}],
                [{'type': 'response.incomplete', 'response': {}}],
                [{'type': 'response.output_text.delta', 'delta': 'partial'}],
                []):
            with self.subTest(events=events), self.assertRaises(RuntimeError):
                list(self.parser.iter_stream(events))
