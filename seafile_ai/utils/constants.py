import os
from enum import Enum

LLM_INPUT_CHARACTERS_LIMIT = 4000
SUMMARY_WORD_LIMIT = int(os.environ.get('SUMMARY_WORD_LIMIT', 50))
SUMMARY_SUPPORTED_FILES = ['.sdoc', '.md', '.markdown', '.docx', '.pdf', '.pptx']

EXTRACT_TEXT_SUPPORTED_IMAGES = ('.gif', '.jpeg', '.jpg', '.png', '.heic', '.ico', '.bmp', '.tif', '.tiff', '.psd', '.webp', '.jfif')

LANGUAGE = {
    'en': 'English',
    'zh-cn': 'Chinese',
    'fr' : 'French',
    'de' : 'German',
    'it' : 'Italian',
}

MODEL_USAGE_STATISTIC_CHANNEL_NAME = 'log_ai_model_usage'


class MODEL_REASONING_TIER(Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'

    @classmethod
    def is_valid(cls, value):
        return value in {item.value for item in cls}


class WritingType:
    ASK = 'ask'
    CONTINUE_WRITING = 'continue_writing'
    MORE_FLUENT = 'more_fluent'
    MORE_DETAILS = 'more_details'
    MORE_CONCISE = 'more_concise'
    MORE_VIVID = 'more_vivid'
