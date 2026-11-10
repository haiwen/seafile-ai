import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from test_llm_tier_config import load_llm_api


class EmbeddingAPITest(unittest.TestCase):
    def setUp(self):
        self.module = load_llm_api({}, {})
        self.embedding = self.module.embedding.litellm.embedding = Mock()
        self.client = self.module.EmbeddingAPI(
            Mock(), 'embedding-model', 'other', 'https://gateway.example/v1', 'test-key',
        )

    def test_batch_preserves_model_parameters_and_sorts_results(self):
        self.embedding.return_value = SimpleNamespace(data=[
            {'index': 1, 'embedding': [4, 5, 6]},
            {'index': 0, 'embedding': ['1', '2', '3']},
        ])

        result = self.client.batch_generate(['first', 'second'], {'repo_id': 'repo-id'})

        self.assertIsInstance(self.client, self.module.BasicLLMAPI)
        self.assertEqual(self.client.model_id, 'embedding-model')
        self.assertEqual(result, [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        self.embedding.assert_called_once_with(
            model='hosted_vllm/embedding-model', input=['first', 'second'], dimensions=3,
            api_base='https://gateway.example/v1', api_key='test-key',
            custom_llm_provider='hosted_vllm', timeout=180,
        )

    def test_generate_returns_single_vector(self):
        self.embedding.return_value = SimpleNamespace(data=[{'index': 0, 'embedding': [1, 2, 3]}])

        self.assertEqual(self.client.generate('first'), [1.0, 2.0, 3.0])
        self.assertEqual(self.embedding.call_args.kwargs['input'], ['first'])

    def test_rejects_invalid_batch_results(self):
        for data, count, message in (
                ([], 1, 'response count mismatch'),
                ([{'index': 1, 'embedding': [1, 2, 3]}], 1, 'indices mismatch'),
                ([{'index': True, 'embedding': [1, 2, 3]}], 1, 'indices mismatch'),
                ([{'index': 0, 'embedding': [1, 2, 3]}] * 2, 2, 'indices mismatch'),
                ([{'index': 0, 'embedding': [1, 2]}], 1, 'dimension mismatch'),
                ([{'index': 0, 'embedding': [1, 2, 'bad']}], 1, 'non-numeric values'),
                ([{'index': 0, 'embedding': [1, 2, float('nan')]}], 1, 'non-finite values'),
                ([{'index': 0, 'embedding': [1, 2, float('inf')]}], 1, 'non-finite values')):
            with self.subTest(data=data):
                self.embedding.return_value = SimpleNamespace(data=data)
                with self.assertLogs(level='ERROR'), self.assertRaisesRegex(ValueError, message):
                    self.client.batch_generate(['first'] * count)
