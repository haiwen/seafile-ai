import inspect
import json
from copy import deepcopy

from seafile_ai.utils import remove_sources_content_and_snippets
from seafile_ai.utils.thought_process_recorder import ThoughtProcessRecorder


def filter_tool_calls_content(tool_name, results):
    if tool_name == 'documents_search':
        return remove_sources_content_and_snippets(deepcopy(results))
    return results


class BasicTool:
    tool = {}

    def register(self, tool_executor, **constant_kwargs):
        tool_executor.register(self.execute, self.tool, **constant_kwargs)

    def execute(self, *args, **kwargs):
        raise NotImplementedError()


class InvalidToolException(Exception):
    pass


class BasicToolExecutor:
    def __init__(self):
        self.cache = {}
        self.thought_process = ThoughtProcessRecorder()
        self.clean()

    def register(self, func, tool_info, **constant_kwargs):
        raise NotImplementedError()

    def clean(self, *args, **kwargs):
        raise NotImplementedError()


class OpenAIToolExecutor(BasicToolExecutor):
    tools = {}

    def clean(self):
        self.tools = {}

    def register(self, func, tool_info, **constant_kwargs):
        name = tool_info.get('function', {}).get('name')
        if not name:
            raise InvalidToolException(tool_info)
        self.tools[name] = {
            'func': func,
            'constant_kwargs': constant_kwargs,
            'tool_info': tool_info,
        }

    def get(self):
        return [tool['tool_info'] for tool in self.tools.values()]

    def execute(self, tool_call, call_back=lambda *args, **kwargs: None):
        function = tool_call['function']
        name = function['name']
        params = json.loads(function.get('arguments', '{}'))
        constant_kwargs = self.tools[name]['constant_kwargs']
        available_params = inspect.signature(self.tools[name]['func']).parameters
        params.update({
            key: value
            for key, value in constant_kwargs.items()
            if key in available_params and key not in params
        })

        if 'tool_executor' in available_params and 'tool_executor' not in params:
            params['tool_executor'] = self
        if 'call_back' in available_params and 'call_back' not in params:
            params['call_back'] = call_back

        return self.tools[name]['func'](**params)
