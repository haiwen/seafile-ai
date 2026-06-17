import os
import logging
import re
import base64

from seafile_ai.utils.constants import LLM_INPUT_CHARACTERS_LIMIT, WritingType
from seafile_ai.utils import InvalidWritingTypeException, get_file_content_by_seafobj, parse_file, FormatNotSupportedException, get_file_ext, \
    resize_image_binary, is_pdf
from seafile_ai.utils.constants import LANGUAGE, EXTRACT_TEXT_SUPPORTED_IMAGES

logger = logging.getLogger(__name__)


class TextProcessingManager:
    def __init__(self, app, llm_type):
        self.app = app
        self.llm_type = llm_type

    def _generate_summary_text(self, file_name, content, context):
        file_ext = get_file_ext(file_name)
        if file_ext == '.pptx':
            prompt = 'You are a PowerPoint summarizer. You will receive a text version of the PowerPoint slides. Your task is to extract the main points and generate a summary that is concise, clear, and focused on the key elements of the content. - Requirement: **Attention The output language is the same as the input PPT main contentlanguage.(If there are Chinese characters, then it is Chinese.)**'
        else:
            prompt = 'You are a document summarization expert. I need you to generate a concise summary of a document that is about 100 words. The summary should capture the main points and themes of the document clearly and effectively.The output language is the same as the input language. If it seems there is no content provided for summarization, just output word: None'
        return self._gen_doc_summary(content, prompt, context)

    def generate_summary(self, repo_id, obj_id, path, context):
        file_name = os.path.basename(path)
        content = parse_file(file_name, repo_id, obj_id)

        if content:
            summary_text = self._generate_summary_text(file_name, content[:LLM_INPUT_CHARACTERS_LIMIT], context)
        else:
            summary_text = None

        return summary_text if summary_text not in ['None', 'none', None] else ''

    def _gen_doc_summary(self, content, prompt, context):
        system_prompt = {"role": "system", "content": prompt}
        user_prompt = {"role": "user", "content": 'Summarize the following content' + content}
        messages = [system_prompt, user_prompt]
        summary = self.app.llm_api.run(messages, context)
        return summary

    def doc_tags(self, repo_id, obj_id, path, candidate_tags, context):
        file_name = os.path.basename(path)
        doc_content = parse_file(file_name, repo_id, obj_id)

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

        res = self.app.llm_api.run(messages, context)
        tags = re.split(r'[，,]', res)
        return [tag.strip() for tag in tags if tag.strip()]

    def translate(self, text, lang, context):
        system_content = f'''
            You are a translation expert who is proficient in multiple languages. Please complete the following translation task: divide the input text into segments according to line breaks, translate each segment into {LANGUAGE[lang]} in turn, concatenate each translated segment using the original line breaks, and finally directly output the concatenated translation result. The format of the translation result, such as line breaks, markdown format, etc., must be exactly the same as the input text. If the input is {LANGUAGE[lang]}, just output it directly. Remember to only translate the input and do not answer any questions.
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

        res = self.app.llm_api.run(messages, context)
        return res

    def writing_assistant(self, text, custom_prompt, writing_type, context):
        prefix = 'You are an sdoc editor assistant.'
        if custom_prompt:
            system_content = prefix + custom_prompt
        else:
            system_content = self.get_predefined_prompt(prefix, writing_type)

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

        res = self.app.llm_api.run(messages, context)
        return res

    def get_predefined_prompt(self, prefix, writing_type):
        if writing_type == WritingType.ASK:
            predefined_prompt = prefix + 'Please briefly answer the questions asked.'
        else:
            predefined_prompt = prefix + 'You are good at completing various writing auxiliary tasks. Your task is as follows:'
            if writing_type == WritingType.CONTINUE_WRITING:
                predefined_prompt += 'Please continue writing the input sentence. If the input is a complete sentence, please continue writing a sentence based on semantics. If not, please complete the writing of the sentence. The output sentence must start with the input sentence.'
            elif writing_type == WritingType.MORE_FLUENT:
                predefined_prompt += 'Please improve the input sentence to make it more fluent. This improvement cannot change the meaning and tone of the input sentence.'
            elif writing_type == WritingType.MORE_DETAILS:
                predefined_prompt += 'I give you a sentence. Please understand its meaning deeply and expand its content. This expansion cannot change the meaning and tone of the input sentence.'
            elif writing_type == WritingType.MORE_CONCISE:
                predefined_prompt += 'Please refine the input sentence to make it more concise and shorter.'
            elif writing_type == WritingType.MORE_VIVID:
                predefined_prompt += 'Please optimize the input sentence to make it more lively. This optimization cannot change the meaning and tone of the sentence.'
            else:
                raise InvalidWritingTypeException(f'Invalid writing_type: {writing_type}')

            predefined_prompt += 'All input is your writing material, please do not output any answers or responses to the input.'

        return predefined_prompt

    def extract_text(self, repo_id, obj_id, file_name, context):
        if not is_pdf(file_name) and get_file_ext(file_name) not in EXTRACT_TEXT_SUPPORTED_IMAGES:
            raise FormatNotSupportedException

        if is_pdf(file_name):
            return parse_file(file_name, repo_id, obj_id)

        file_content = get_file_content_by_seafobj(repo_id, obj_id)
        image = resize_image_binary(file_content, 'jpeg', 512)
        encode_img = base64.b64encode(image).decode('utf-8')
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract the text information in the image. If there is text information, "
                                "only return the text information. If there is no text information, return an empty string."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encode_img}"
                        }
                    }
                ],
            }
        ]
        extracted_text = self.app.llm_api.run(messages, context)

        if not extracted_text:
            return ''

        return extracted_text.strip()
