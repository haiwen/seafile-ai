import json
import re
from html import escape
from html.parser import HTMLParser


SDOC_TAG_RE = re.compile(
    r'<seafile-ai-seadoc\b(?P<attributes>(?:[^>"\']|"[^"]*"|\'[^\']*\')*?)'
    r'(?:\s*/>|>[\s\S]*?</seafile-ai-seadoc>)'
)


class SdocReferenceParser(HTMLParser):
    sdoc_create_uuid = None

    def handle_starttag(self, tag, attrs):
        identifiers = [value for key, value in attrs if key == 'sdoc_create_uuid']
        if tag == 'seafile-ai-seadoc' and len(identifiers) == 1:
            self.sdoc_create_uuid = identifiers[0]


def resolve_sdoc_results(answer, tool_executor):
    """Expand references using only content validated and cached by this request's tool."""
    cached_results = tool_executor.cache.get('sdoc_create_results', {})

    def replace(match):
        parser = SdocReferenceParser()
        parser.feed('<seafile-ai-seadoc%s>' % match.group('attributes'))
        identifier = parser.sdoc_create_uuid
        cached = cached_results.get(identifier)
        if cached is None:
            return ''
        # Never use model-supplied metadata or content, even when it changes the tag shape.
        attributes = ' '.join('%s="%s"' % (key, escape(value, quote=True)) for key, value in (
            ('sdoc_create_uuid', identifier), ('file_name', cached['file_name']),
            ('description', cached['description'])))
        body = json.dumps(cached['content'], ensure_ascii=False, allow_nan=False)
        body = body.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
        return '<seafile-ai-seadoc %s>\n%s\n</seafile-ai-seadoc>' % (attributes, body)

    pattern = re.compile(
        r'(?P<code>```[\s\S]*?```|~~~[\s\S]*?~~~|`+[^`\n]*`+|'
        r'<seafile-ai-markdown\b[^>]*>[\s\S]*?</seafile-ai-markdown>)|' + SDOC_TAG_RE.pattern
    )
    return pattern.sub(lambda match: match.group(0) if match.group('code') else replace(match), answer)
