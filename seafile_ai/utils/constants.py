LLM_INPUT_CHARACTERS_LIMIT = 4000
SUMMARY_SUPPORTED_FILES = ['.sdoc', '.md', '.markdown', '.docx', '.pdf', '.pptx']

LANGUAGE = {
    'en': 'English',
    'zh-cn': 'Chinese',
}


class WritingType:
    ASK = 'ask'
    CONTINUE_WRITING = 'continue_writing'
    MORE_FLUENT = 'more_fluent'
    MORE_DETAILS = 'more_details'
    MORE_CONCISE = 'more_concise'
    MORE_VIVID = 'more_vivid'
