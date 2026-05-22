class ChatCallBacker:
    def __init__(self):
        self.execution_detail = {}

    def __call__(self, func, *args, **kwargs):
        if func != 'update_execution_detail':
            return
        data = args[0]
        for key, value in data.items():
            self.execution_detail['%s. %s' % (len(self.execution_detail) + 1, key)] = value
