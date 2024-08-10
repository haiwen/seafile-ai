class MetadataTable(object):
    def __init__(self, table_id, name):
        self.id = table_id
        self.name = name

    @property
    def columns(self):
        return MetadataColumns()


class MetadataColumns(object):
    def __init__(self):
        self.id = MetadataColumn('_id', '_id', 'text')
        self.file_name = MetadataColumn('_name', '_name', 'text')
        self.parent_dir = MetadataColumn('_parent_dir', '_parent_dir', 'text')
        self.summary = MetadataColumn('_summary', '_summary', 'long-text')


class MetadataColumn(object):
    def __init__(self, key, name, type, data=None):
        self.key = key
        self.name = name
        self.type = type
        self.data = data

    def to_dict(self):
        column_data = {
            'key': self.key,
            'name': self.name,
            'type': self.type,
        }
        if self.data:
            column_data['data'] = self.data

        return column_data


METADATA_TABLE = MetadataTable('0001', 'Table1')
