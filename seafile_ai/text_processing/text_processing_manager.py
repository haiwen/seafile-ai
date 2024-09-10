import os
import logging

from pathlib import Path

from seafile_ai.utils.constants import LLM_INPUT_CHARACTERS_LIMIT, SUMMARY_SUPPORTED_FILES
from seafile_ai.utils import convert_file_to_md


logger = logging.getLogger(__name__)


class TextProcessingManager:
    def __init__(self, app, llm_type):
        self.app = app
        self.llm_type = llm_type

    def generate_summary(self, path, download_token):
        file_name = os.path.basename(path)

        if md_content := convert_file_to_md(file_name, download_token):
            summary_text = self._gen_doc_summary(md_content[0:LLM_INPUT_CHARACTERS_LIMIT])
        else:
            summary_text = None

        if summary_text in ['None', 'none', None]:
            return ''

        return summary_text

    def _gen_doc_summary(self, content):
        if self.llm_type == 'open-ai-proxy':
            system_content = 'You are a document summarization expert. I need you to generate a concise summary of a document that is about 100 words. The summary should capture the main points and themes of the document clearly and effectively.The output language is the same as the input language. If it seems there is no content provided for summarization, just output word: None'
            system_prompt = {"role": "system", "content": system_content}
            user_prompt = {"role": "user", "content": content}
            messages = [system_prompt, user_prompt]
            summary = self.app.openai_api.chat_completions(messages)
            return summary
        else:
            logger.error('llm_type is not set correctly in config')
            return None
