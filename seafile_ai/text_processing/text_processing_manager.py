import os
import logging

from pathlib import Path

from seafile_ai.utils.constants import LLM_INPUT_CHARACTERS_LIMIT
from seafile_ai.utils import parse_file


logger = logging.getLogger(__name__)


class TextProcessingManager:
    def __init__(self, app, llm_type):
        self.app = app
        self.llm_type = llm_type

    def _generate_summary_text(self, file_name, content):
        file_ext = Path(file_name).suffix.lower()
        if file_ext == '.pptx':
            prompt = 'You are a PowerPoint summarizer. You will receive a text version of the PowerPoint slides. Your task is to extract the main points and generate a summary that is concise, clear, and focused on the key elements of the content. - Requirement: **Attention The output language is the same as the input PPT main contentlanguage.(If there are Chinese characters, then it is Chinese.)**'
        else:
            prompt = 'You are a document summarization expert. I need you to generate a concise summary of a document that is about 100 words. The summary should capture the main points and themes of the document clearly and effectively.The output language is the same as the input language. If it seems there is no content provided for summarization, just output word: None'
        return self._gen_doc_summary(content, prompt)

    def generate_summary(self, path, download_token):
        file_name = os.path.basename(path)
        content = parse_file(file_name, download_token)

        if content:
            summary_text = self._generate_summary_text(file_name, content[:LLM_INPUT_CHARACTERS_LIMIT])
        else:
            summary_text = None

        return summary_text if summary_text not in ['None', 'none', None] else ''

    def _gen_doc_summary(self, content, prompt):
        if self.llm_type == 'open-ai-proxy':
            system_prompt = {"role": "system", "content": prompt}
            user_prompt = {"role": "user", "content": 'Summarize the following content' + content}
            messages = [system_prompt, user_prompt]
            summary = self.app.openai_api.chat_completions(messages)
            return summary
        else:
            logger.error('llm_type is not set correctly in config')
            return None
