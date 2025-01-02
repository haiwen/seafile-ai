import os
import logging
import re

from pathlib import Path

from seafile_ai.utils.constants import LLM_INPUT_CHARACTERS_LIMIT, WritingType
from seafile_ai.utils import InvalidWritingTypeException, parse_file
from seafile_ai.utils.constants import LANGUAGE


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

    def doc_tags(self, path, download_token, candidate_tags):
        file_name = os.path.basename(path)
        doc_content = parse_file(file_name, download_token)

        if not doc_content:
            return None

        system_content = f'''
            You are a key phrase extractor. I will provide you with a document in Markdown format and a set of reference phrases. You need to complete two tasks in sequence:
            1、Key Phrase Extraction: Identify a set of up to 10 key phrases from the document. Each key phrase should consist of at most three words, and there should be no semantic overlap between the phrases. The phrases must be common and appear in the document.
            2、Semantic Similarity and Replacement: For each key phrase identified in task 1, calculate its semantic similarity with each reference phrase. If the similarity exceeds 0.9, replace the key phrase with the corresponding reference phrase.
            Finally, output the resulting key phrases, separated by commas. Do not include anything other than the key phrases and commas.
            Reference phrases: {','.join(candidate_tags)}
        '''

        system_prompt = {
            "role": "system",
            "content": system_content
        }
        user_prompt = {
            "role": "user",
            "content": doc_content
        }
        messages = [system_prompt, user_prompt]

        res = self.app.openai_api.chat_completions(messages)
        tags = re.split(r'[，,]', res)
        return [tag.strip() for tag in tags if tag.strip()]

    def translate(self, text, lang):
        system_content = f'''
            You are a translator who is proficient in various languages. Please translate the input into {LANGUAGE[lang]} and output the translation results directly. If the input is in {LANGUAGE[lang]}, just output the input as it is. Remember to only translate the input and do not answer any questions.
        '''

        system_prompt = {
            "role": "system",
            "content": system_content
        }
        user_prompt = {
            "role": "user",
            "content": text
        }
        messages = [system_prompt, user_prompt]

        res = self.app.openai_api.chat_completions(messages)
        return res

    def writing_assistant(self, text, writing_type):
        system_content = 'You are an sdoc editor assistant.'
        if writing_type == WritingType.ASK:
            system_content += 'Please briefly answer the questions asked.'
        else:
            system_content += 'You are good at completing various writing auxiliary tasks. Your task is as follows:'
            if writing_type == WritingType.CONTINUE_WRITING:
                system_content = 'Please continue writing the input sentence. If the input is a complete sentence, please continue writing a sentence based on semantics. If not, please complete the writing of the sentence. The output sentence must start with the input sentence.'
            elif writing_type == WritingType.MORE_DETAILS:
                system_content = 'I give you a sentence. Please understand its meaning deeply and expand its content. This expansion cannot change the meaning and tone of the input sentence.'
            elif writing_type == WritingType.MORE_CONCISE:
                system_content = 'Please refine the input sentence to make it more concise and shorter.'
            elif writing_type == WritingType.MORE_VIVID:
                system_content = 'Please optimize the input sentence to make it more lively. This optimization cannot change the meaning and tone of the sentence.'
            else:
                raise InvalidWritingTypeException(f'Invalid writing_type: {writing_type}')

            system_content += 'All input is your writing material, please do not output any answers or responses to the input.'

        system_content += 'No need to interact with the user, just output the results directly.'

        system_prompt = {
            "role": "system",
            "content": system_content
        }
        user_prompt = {
            "role": "user",
            "content": text
        }
        messages = [system_prompt, user_prompt]

        res = self.app.openai_api.chat_completions(messages)
        return res
