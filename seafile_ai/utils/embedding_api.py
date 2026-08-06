import logging
import math

import litellm


logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = 1536


class EmbeddingAPI:
    def __init__(self, model, model_type='openai', base_url=None, api_key=None, timeout=30):
        if model_type == 'other':
            model_type = 'hosted_vllm'
        self.model_id = model
        self.model_type = model_type
        self.model = f'{model_type}/{model}' if model_type else model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout

    def _validate_embeddings(self, embeddings, expected_count):
        if not isinstance(embeddings, list) or len(embeddings) != expected_count:
            raise ValueError('Embedding response count mismatch')
        normalized_embeddings = []
        for embedding in embeddings:
            if not isinstance(embedding, list) or len(embedding) != EMBEDDING_DIMENSIONS:
                raise ValueError('Embedding dimension mismatch')
            try:
                normalized_embedding = [float(value) for value in embedding]
            except (TypeError, ValueError):
                raise ValueError('Embedding contains non-numeric values')
            if not all(math.isfinite(value) for value in normalized_embedding):
                raise ValueError('Embedding contains non-finite values')
            normalized_embeddings.append(normalized_embedding)
        return normalized_embeddings

    def batch_generate(self, contents, context=None):
        if not isinstance(contents, list) or not contents or not all(isinstance(content, str) and content for content in contents):
            raise ValueError('Embedding contents are invalid')

        try:
            response = litellm.embedding(
                model=self.model,
                input=contents,
                api_base=self.base_url,
                api_key=self.api_key,
                custom_llm_provider=self.model_type,
                timeout=self.timeout,
            )
            if not isinstance(response.data, list) or len(response.data) != len(contents):
                raise ValueError('Embedding response count mismatch')
            indices = [item.get('index') for item in response.data]
            if (
                not all(isinstance(index, int) and not isinstance(index, bool) for index in indices)
                or set(indices) != set(range(len(contents)))
            ):
                raise ValueError('Embedding response indices mismatch')
            embeddings = [
                item.get('embedding')
                for item in sorted(response.data, key=lambda item: item.get('index'))
            ]
            return self._validate_embeddings(embeddings, len(contents))
        except Exception as error:
            logger.error('Embedding generation failed: %s', error)
            raise

    def generate(self, content, context=None):
        return self.batch_generate([content], context)[0]
