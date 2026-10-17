import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from test_llm_tier_config import load_llm_api


class LLMTemperatureTest(unittest.TestCase):
    def setUp(self):
        self.module = load_llm_api({}, {})
        self.response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='result'))],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        )
        self.module.litellm.completion = Mock(return_value=self.response)
        self.messages = [{'role': 'user', 'content': 'Describe this file.'}]

    def test_claude_omits_temperature_for_direct_and_gateway_requests(self):
        for model in (
                'claude-sonnet-5-5', 'claude-opus-5-5', 'claude-opus-4-7',
                'claude-sonnet-4-5', 'claude-3-5-sonnet-20241022',
                'anthropic/claude-opus-5-5', 'Claude-Sonnet-5-5'):
            for provider in ('anthropic', 'other', 'openai'):
                for method in ('run', 'completion'):
                    for params in ({}, {'temperature': 0}, {'temperature': 0.1}):
                        with self.subTest(model=model, provider=provider, method=method, params=params):
                            client = self.module.LLMAPI(
                                Mock(), model, provider, base_url='https://gateway.example/v1',
                            )
                            result = getattr(client, method)(messages=self.messages, **params)

                            request = self.module.litellm.completion.call_args.kwargs
                            self.assertNotIn('temperature', request)
                            self.assertEqual(request['messages'], self.messages)
                            self.assertEqual(
                                request['custom_llm_provider'],
                                'hosted_vllm' if provider == 'other' else provider,
                            )
                            if method == 'run':
                                self.assertEqual(result, 'result')
                            else:
                                self.assertIs(result, self.response)

    def test_other_models_keep_temperature_behavior(self):
        for model, provider, params, expected in (
                ('gpt-4o', 'openai', {}, 0),
                ('gpt-4o', 'openai', {'temperature': 0.2}, 0.2),
                ('qwen-3', 'other', {}, 0),
                ('qwen-3', 'other', {'temperature': 0.2}, 0.2),
                ('gpt-5', 'openai', {}, 1),
                ('gpt-5', 'openai', {'temperature': 0.2}, 1)):
            with self.subTest(model=model, provider=provider, params=params):
                client = self.module.LLMAPI(
                    Mock(), model, provider, base_url='https://gateway.example/v1',
                )
                client.run(self.messages, **params)

                request = self.module.litellm.completion.call_args.kwargs
                self.assertEqual(request['temperature'], expected)
