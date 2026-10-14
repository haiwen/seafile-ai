import base64
import ast
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

import requests
import jwt
from flask import Flask, Response, request
from PIL import Image

spec = importlib.util.spec_from_file_location(
    'cover_client', Path(__file__).resolve().parents[1] / 'seafile_ai/utils/image_generation_api.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def result():
    buffer = io.BytesIO()
    Image.new('RGB', (64, 32)).save(buffer, format='PNG')
    return {'status': 'completed', 'output': [{
        'type': 'image_generation_call', 'status': 'completed',
        'result': base64.b64encode(buffer.getvalue()).decode(),
    }]}


class CoverGenerationTest(unittest.TestCase):
    def setUp(self):
        self.client = module.ImageGenerationAPI({
            'model': 'gpt-6.1-sol', 'url': 'https://example.test/v1/', 'key': 'test-key',
        })

    def test_decodes_single_valid_image(self):
        content = self.client.decode_image(result())
        with Image.open(io.BytesIO(content)) as image:
            self.assertEqual(image.size, (64, 32))
            self.assertEqual(image.format, 'PNG')

    def test_rejects_text_incomplete_multiple_and_invalid_images(self):
        cases = [
            {'status': 'completed', 'output': [{'type': 'message'}]},
            {'status': 'incomplete', 'output': []},
            {'status': 'completed', 'output': result()['output'] * 2},
            {'status': 'completed', 'output': [{'type': 'image_generation_call', 'status': 'completed', 'result': '!!!'}]},
            {'status': 'completed', 'output': [{'type': 'image_generation_call', 'status': 'completed', 'result': base64.b64encode(b'not image').decode()}]},
        ]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(module.CoverGenerationError):
                self.client.decode_image(data)

    def test_input_rejected_before_request(self):
        with patch.object(module.requests, 'post') as post:
            for prompt in (None, '', ' ', 'a' * 2001, []):
                with self.assertRaises(module.CoverGenerationError) as error:
                    self.client.generate_cover(prompt)
                self.assertEqual(error.exception.status, 400)
            post.assert_not_called()

    def test_sends_responses_tool_without_chat_or_retry(self):
        import json
        response = Mock(status_code=200)
        response.iter_content.return_value = [json.dumps(result()).encode()]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(module.requests, 'post', return_value=response) as post:
            self.client.generate_cover('mountains')
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://example.test/v1/responses')
        self.assertEqual(kwargs['json']['model'], 'gpt-6.1-sol')
        self.assertEqual(kwargs['json']['tool_choice'], {'type': 'image_generation'})
        self.assertEqual(kwargs['json']['tools'][0]['model'], 'gpt-image-2')
        self.assertFalse(kwargs['json']['store'])
        self.assertFalse(kwargs['allow_redirects'])

    def test_timeout_is_not_retried(self):
        with patch.object(module.requests, 'post', side_effect=requests.Timeout) as post:
            with self.assertRaises(module.CoverGenerationError) as error:
                self.client.generate_cover('mountains')
        self.assertEqual(error.exception.status, 504)
        post.assert_called_once()

    def test_response_size_limit(self):
        response = Mock(status_code=200)
        response.iter_content.return_value = [b'x' * 32]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(module, 'MAX_RESPONSE_BYTES', 16), patch.object(module.requests, 'post', return_value=response):
            with self.assertRaises(module.CoverGenerationError):
                self.client.generate_cover('mountains')


class CoverGenerationEndpointTest(unittest.TestCase):
    def setUp(self):
        # Isolate this route from unrelated chat/database imports.
        path = Path(__file__).resolve().parents[1] / 'seafile_ai/server/apis.py'
        source = ast.parse(path.read_text())
        route = next(node for node in source.body
                     if isinstance(node, ast.FunctionDef) and node.name == 'generate_cover_image')
        self.app = Flask(__name__)
        self.generator = Mock()
        self.app.app = SimpleNamespace(image_generation_api=self.generator)
        context = {'flask_app': self.app, 'request': request, 'Response': Response,
                   'jwt': jwt, 'config': SimpleNamespace(SECRET_KEY='test-secret-for-unit-tests-only-32-bytes'),
                   'CoverGenerationError': module.CoverGenerationError, 'logger': Mock()}
        exec(compile(ast.Module(body=[route], type_ignores=[]), str(path), 'exec'), context)
        self.client = self.app.test_client()
        import time
        self.headers = {'Authorization': 'Token ' + jwt.encode(
            {'exp': int(time.time()) + 300}, 'test-secret-for-unit-tests-only-32-bytes', algorithm='HS256')}

    def test_service_authentication_requires_expiration(self):
        for headers in ({}, {'Authorization': 'Token bad'}, {'Authorization': 'Token ' +
                jwt.encode({}, 'test-secret-for-unit-tests-only-32-bytes', algorithm='HS256')}):
            self.assertEqual(self.client.post('/api/v1/generate-cover-image/',
                                             json={'prompt': 'mountains'}, headers=headers).status_code, 403)
        self.generator.generate_cover.assert_not_called()

    def test_availability_does_not_generate(self):
        response = self.client.get('/api/v1/generate-cover-image/', headers=self.headers)
        self.assertEqual(response.json, {'available': True})
        self.generator.generate_cover.assert_not_called()
        self.app.app.image_generation_api = None
        response = self.client.post('/api/v1/generate-cover-image/', json={'prompt': 'test'}, headers=self.headers)
        self.assertEqual(response.status_code, 503)

    def test_success_and_failure(self):
        self.generator.generate_cover.return_value = b'png'
        response = self.client.post('/api/v1/generate-cover-image/', json={'prompt': 'test'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'image/png')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.generator.generate_cover.side_effect = module.CoverGenerationError('Timed out', 504)
        response = self.client.post('/api/v1/generate-cover-image/', json={'prompt': 'test'}, headers=self.headers)
        self.assertEqual(response.status_code, 504)


class CoverModelConfigTest(unittest.TestCase):
    def test_explicit_selection_never_falls_back(self):
        path = Path(__file__).resolve().parents[1] / 'seafile_ai/config.py'
        for selected, expected in (('', None), ('missing', None), ('gpt-6.1-sol', 'gpt-6.1-sol')):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as directory:
                Path(directory, 'seafile_ai_config.yaml').write_text(
                    'global:\n'
                    '  LLM_MODELS:\n'
                    '    - type: other\n'
                    '      model: chat-model\n'
                    '      url: https://example.test/v1\n'
                    '      key: test-key\n'
                    '      default: true\n'
                    '    - type: other\n'
                    '      model: gpt-6.1-sol\n'
                    '      url: https://example.test/v1\n'
                    '      key: test-key\n'
                    f'  AI_COVER_MODEL: "{selected}"\n'
                )
                with patch.dict(os.environ, {'CONF_PATH': directory}, clear=True):
                    spec = importlib.util.spec_from_file_location('cover_config_test', path)
                    config = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(config)
                self.assertEqual(config.DEFAULT_LLM_MODEL['model'], 'chat-model')
                self.assertEqual(config.AI_COVER_MODEL_CONFIG['model']
                                 if config.AI_COVER_MODEL_CONFIG else None, expected)


if __name__ == '__main__':
    unittest.main()
