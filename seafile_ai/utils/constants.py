LLM_INPUT_CHARACTERS_LIMIT = 4000
SUMMARY_SUPPORTED_FILES = ['.sdoc', '.md', '.markdown', '.docx', '.pdf', '.pptx']

LANGUAGE = {
    'en': 'English',
    'zh-cn': 'Chinese',
}


class WritingType:
    ASK = 'ask'
    CONTINUE_WRITING = 'continue_writing'
    MORE_DETAILED = 'more_detailed'
    MORE_CONCISE = 'more_concise'
    MORE_LIVELY = 'more_lively'
