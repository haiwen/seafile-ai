import os

LLM_INPUT_CHARACTERS_LIMIT = 4000
SUMMARY_CHARACTER_LIMIT = int(os.environ.get('SUMMARY_CHARACTER_LIMIT', 100))
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

class WritingType:
    ASK = 'ask'
    CONTINUE_WRITING = 'continue_writing'
    MORE_FLUENT = 'more_fluent'
    MORE_DETAILS = 'more_details'
    MORE_CONCISE = 'more_concise'
    MORE_VIVID = 'more_vivid'
