import json


class SSE:
    @staticmethod
    def data(obj):
        return 'data: %s\n\n' % json.dumps(obj)

    @staticmethod
    def status(status, detail=None):
        return SSE.data({
            'status': {
                'type': status,
                'detail': detail,
            }
        })

    @staticmethod
    def answer(content):
        if not content:
            return None
        return SSE.data({'answer': content})

    @staticmethod
    def search_found(number):
        return SSE.data({'search_found': number})

    @staticmethod
    def results(answer, sources, thought_process):
        return SSE.data({
            'results': {
                'answer': answer,
                'sources': sources,
                'thought_process': thought_process,
            }
        })

    @staticmethod
    def done():
        return 'data: [DONE]\n\n'

    @staticmethod
    def error(error_msg):
        return f'data: [ERROR: {error_msg}]\n\n'
