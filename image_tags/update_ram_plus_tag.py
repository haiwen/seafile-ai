import requests
from seatable_api import Base
from tqdm import tqdm
import config
import os
import torch
from clip import clip


def list_rows(api_token, table_name):
    server_url = 'https://dev.seatable.cn'

    base = Base(api_token, server_url)
    base.auth()
    all_rows = []
    while True:
        rows = base.list_rows(table_name, start=len(all_rows), limit=1000)
        all_rows.extend(rows)
        if len(rows) < 1000:
            break

    return all_rows


def generate_tag_des(tag):
    # Generate LLM tag descriptions

    llm_prompts = [f"Describe concisely what a(n) {tag} looks like:",
                   f"How can you identify a(n) {tag} concisely?",
                   f"What does a(n) {tag} look like concisely?",
                   f"What are the identifying characteristics of a(n) {tag}:",
                   f"Please provide a concise description of the visual characteristics of {tag}:"]
    openai_url = 'http://docs-stg.seafile.com/api/v1/chat-completions/create'

    result_lines = []
    result_lines.append(f"a photo of a {tag}.")

    for llm_prompt in tqdm(llm_prompts):
        json_data = {
            'model': "gpt-4o-mini",
            'messages': [{"role": "assistant", "content": llm_prompt}],
            'max_tokens': 77,
            'temperature': 0.99,
            'n': 10,
            'stop': None,
        }
        response = requests.post(openai_url, json=json_data, timeout=30)
        response = response.json()

        # parse the response
        for item in response['choices']:
            result_lines.append(item['message']['content'].strip())
    return result_lines


def save_tag_des(tag, tag_descriptions):
    server_url = 'https://dev.seatable.cn'
    api_token = 'e50cb810023bd54efd6285bbb3c6aef4105777f3'

    base = Base(api_token, server_url)
    base.auth()
    rows_data = [{
        'tag': tag,
        'description': tag_description
    } for tag_description in tag_descriptions]
    res = base.batch_append_rows("New Tags Description", rows_data)
    print(res)


def encode_label(descriptions):
    print("Creating pretrained CLIP model")
    model, _ = clip.load("ViT-B/16")

    run_on_gpu = torch.cuda.is_available()

    texts = clip.tokenize(descriptions, truncate=True)  # tokenize
    if run_on_gpu:
        texts = texts.cuda()
        model = model.cuda()
    text_embeddings = model.encode_text(texts)
    text_embeddings /= text_embeddings.norm(dim=-1, keepdim=True)

    return text_embeddings


if __name__ == '__main__':
    # need install clip package (pip install git+https://github.com/openai/CLIP.git)
    model_dir = config.IMAGE_TAGS_MODEL_DIR
    embedding_dict_path = os.path.join(model_dir, 'ram_plus_swin_large_14m_label_embed_dict.pth')
    embedding_dict = torch.load(embedding_dict_path, map_location='cpu', weights_only=True)

    tags_dir = os.path.join(model_dir, 'tags')
    os.makedirs(tags_dir, exist_ok=True)
    tags_threshold_file = open(os.path.join(tags_dir, 'tags_threshold.txt'), 'w')
    english_tags_file = open(os.path.join(tags_dir, 'english_tags.txt'), 'w')
    chinese_tags_file = open(os.path.join(tags_dir, 'chinese_tags.txt'), 'w')

    api_token = 'e50cb810023bd54efd6285bbb3c6aef4105777f3'
    tag_rows = list_rows(api_token, "RAM")
    description_rows = list_rows(api_token, "New Tags Description")
    label_descriptions_dict = {}
    for row in description_rows:
        label = row['tag']
        description = row['description']
        if label not in label_descriptions_dict:
            label_descriptions_dict[label] = [description]
        else:
            label_descriptions_dict[label].append(description)

    label_embeddings = None
    for index, row in tqdm(enumerate(tag_rows)):
        if row.get('delete'):
            continue

        chinese_tag = row['tag(zh-cn)']
        english_tag = row['tag(en)']
        threshold = row.get('threshold') or 0.5
        embedding = embedding_dict.get(english_tag)
        if embedding is None:
            label_descriptions = label_descriptions_dict.get(english_tag)
            if not label_descriptions:
                label_descriptions = generate_tag_des(english_tag)
                save_tag_des(english_tag, label_descriptions)
            embedding = encode_label(label_descriptions)
        label_embeddings = torch.cat((label_embeddings, embedding), dim=0) if label_embeddings is not None else embedding

        tags_threshold_file.write(str(threshold) + '\n')
        english_tags_file.write(english_tag.strip() + '\n')
        chinese_tags_file.write(chinese_tag.strip() + '\n')

    torch.save({'label_embed': label_embeddings}, os.path.join(model_dir, 'ram_plus_swin_large_14m_label_embed.pth'))
