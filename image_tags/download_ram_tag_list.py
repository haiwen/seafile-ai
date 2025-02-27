from seatable_api import Base
import config
import os


def query_rows():
    server_url = 'https://dev.seatable.cn'
    api_token = 'e50cb810023bd54efd6285bbb3c6aef4105777f3'

    base = Base(api_token, server_url)
    base.auth()
    all_rows = []
    while True:
        rows = base.list_rows("RAM", start=len(all_rows), limit=1000)
        all_rows.extend(rows)
        if len(rows) < 1000:
            break

    return all_rows


if __name__ == '__main__':
    model_dir = config.IMAGE_TAGS_MODEL_DIR
    tags_dir = os.path.join(model_dir, 'tags')
    os.makedirs(tags_dir, exist_ok=True)
    tags_threshold_file = open(os.path.join(tags_dir, 'tags_threshold.txt'), 'w')
    english_tags_file = open(os.path.join(tags_dir, 'english_tags.txt'), 'w')
    chinese_tags_file = open(os.path.join(tags_dir, 'chinese_tags.txt'), 'w')
    deleted_tags_index_file = open(os.path.join(tags_dir, 'deleted_tags_index.txt'), 'w')

    rows = query_rows()

    for index, row in enumerate(rows):
        chinese_tag = row['tag(zh-cn)']
        english_tag = row['tag(en)']
        threshold = row['threshold']

        tags_threshold_file.write(str(threshold) + '\n')
        english_tags_file.write(english_tag.strip() + '\n')
        chinese_tags_file.write(chinese_tag.strip() + '\n')
        if row.get('delete'):
            deleted_tags_index_file.write(str(index) + '\n')
