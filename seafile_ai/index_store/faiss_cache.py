from collections import OrderedDict


class FaissCache(object):

    def __init__(self, max_size=200):
        self.index_cache = OrderedDict()
        self.max_size = max_size

    def get(self, key):
        return self.index_cache.get(key)

    def set(self, key, value):
        if not self.index_cache.get(key) and self.size == self.max_size:
            self.delete_first()
        self.index_cache[key] = value

    def delete(self, key):
        return self.index_cache.pop(key, None)

    def delete_first(self):
        return self.index_cache.popitem(last=False)

    @property
    def size(self):
        return len(self.index_cache)
