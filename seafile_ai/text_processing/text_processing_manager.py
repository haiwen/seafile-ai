import os
import logging

from seafile_ai.utils.sdoc2md import sdoc2md
from seafile_ai.utils.constants import LLM_INPUT_CHARACTERS_LIMIT
from seafile_ai.utils import get_file_by_token


logger = logging.getLogger(__name__)


class TextProcessingManager:
    def __init__(self, app, llm_type):
        self.app = app
        self.llm_type = llm_type

    def generate_summary(self, path, download_token):
        file_name = os.path.basename(path)
        sdoc_content = get_file_by_token(download_token, file_name)
        md_content = sdoc2md(sdoc_content)[0:LLM_INPUT_CHARACTERS_LIMIT]
        summary_text = self._gen_doc_summary(md_content)
        if summary_text in ['None', 'none', None]:
            summary_text = ''

        return summary_text

    def _gen_doc_summary(self, content):
        if self.llm_type == 'open-ai-proxy':
            system_content = 'You are a document summarization expert. I need you to generate a concise summary of a document that is no longer than 40 words. The summary should capture the main points and themes of the document clearly and effectively.The output language is the same as the input language. If it seems there is no content provided for summarization, just output word: None'
            system_prompt = {"role": "system", "content": system_content}
            user_prompt = {"role": "user", "content": content}
            messages = [system_prompt, user_prompt]
            summary = self.app.openai_api.chat_completions(messages)
            return summary
        else:
            logger.error('llm_type is not set correctly in config')
            return None
