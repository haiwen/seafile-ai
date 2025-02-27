import os

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

from .bert import BertConfig, BertModel
from .swin_transformer import SwinTransformer
from .utils import read_json, init_tokenizer


class RAM_plus(nn.Module):
    def __init__(self, model_dir, threshold=0.68):
        super().__init__()

        # create image encoder
        vision_config_path = os.path.join(model_dir, 'config_swinL_384.json')
        vision_config = read_json(vision_config_path)
        vision_width = vision_config['vision_width']

        self.visual_encoder = SwinTransformer(
            img_size=vision_config['image_res'],
            patch_size=4,
            in_chans=3,
            embed_dim=vision_config['embed_dim'],
            depths=vision_config['depths'],
            num_heads=vision_config['num_heads'],
            window_size=vision_config['window_size'],
            mlp_ratio=4.,
            qkv_bias=True,
            drop_rate=0.0,
            drop_path_rate=0.1,
            ape=False,
            patch_norm=True,
            use_checkpoint=False)

        # create tokenzier
        self.tokenizer = init_tokenizer(os.path.join(model_dir, 'tokenizer'))

        # load tag list
        self.tags_dir = os.path.join(model_dir, 'tags')
        self.english_tag_list = self.load_tag_list(os.path.join(self.tags_dir, 'english_tags.txt'))
        self.chinese_tag_list = self.load_tag_list(os.path.join(self.tags_dir, 'chinese_tags.txt'))

        # create image-tag recognition decoder
        self.threshold = threshold
        self.num_class = len(self.english_tag_list)
        q2l_config = BertConfig.from_json_file(os.path.join(model_dir, 'q2l_config.json'))
        q2l_config.encoder_width = 512
        self.tagging_head = BertModel(config=q2l_config,
                                      add_pooling_layer=False)
        self.tagging_head.resize_token_embeddings(len(self.tokenizer))
        self.label_embed = nn.Parameter(torch.zeros(self.num_class * 51, q2l_config.encoder_width))

        self.wordvec_proj = nn.Linear(512, q2l_config.hidden_size)

        self.fc = nn.Linear(q2l_config.hidden_size, 1)

        self.del_selfattention()

        self.image_proj = nn.Linear(vision_width, 512)

        # adjust thresholds for some tags
        self.class_threshold = torch.ones(self.num_class) * self.threshold
        ram_class_threshold_path = os.path.join(self.tags_dir, 'tags_threshold.txt')
        with open(ram_class_threshold_path, 'r', encoding='utf-8') as f:
            ram_class_threshold = [float(s.strip()) for s in f]
        for key, value in enumerate(ram_class_threshold):
            self.class_threshold[key] = value

        self.reweight_scale = nn.Parameter(torch.ones([]) * np.log(1 / 0.07))

    def load_tag_list(self, tag_list_file):
        with open(tag_list_file, 'r', encoding="utf-8") as f:
            tag_list = f.read().splitlines()
        tag_list = np.array(tag_list)
        return tag_list

    # delete self-attention layer of image-tag recognition decoder to reduce computation, follower Query2Label
    def del_selfattention(self):
        del self.tagging_head.embeddings
        for layer in self.tagging_head.encoder.layer:
            del layer.attention

    def predict(self, image, lang):
        if lang == 'en':
            tag_list = self.english_tag_list
        elif lang == 'zh-cn':
            tag_list = self.chinese_tag_list
        else:
            raise Exception('not support language: {}'.format(lang))

        image_embeds = self.image_proj(self.visual_encoder(image))
        image_atts = torch.ones(image_embeds.size()[:-1],
                                dtype=torch.long).to(image.device)

        image_cls_embeds = image_embeds[:, 0, :]
        image_spatial_embeds = image_embeds[:, 1:, :]

        bs = image_spatial_embeds.shape[0]

        des_per_class = int(self.label_embed.shape[0] / self.num_class)

        image_cls_embeds = image_cls_embeds / image_cls_embeds.norm(dim=-1, keepdim=True)
        reweight_scale = self.reweight_scale.exp()
        logits_per_image = (reweight_scale * image_cls_embeds @ self.label_embed.t())
        logits_per_image = logits_per_image.view(bs, -1, des_per_class)

        weight_normalized = F.softmax(logits_per_image, dim=2)
        label_embed_reweight = torch.empty(bs, self.num_class, 512).to(image.device).to(image.dtype)

        for i in range(bs):
            reshaped_value = self.label_embed.view(-1, des_per_class, 512)
            product = weight_normalized[i].unsqueeze(-1) * reshaped_value
            label_embed_reweight[i] = product.sum(dim=1)

        label_embed = torch.nn.functional.relu(self.wordvec_proj(label_embed_reweight))

        # recognized image tags using alignment decoder
        tagging_embed = self.tagging_head(
            encoder_embeds=label_embed,
            encoder_hidden_states=image_embeds,
            encoder_attention_mask=image_atts,
            return_dict=False,
            mode='tagging',
        )

        logits = self.fc(tagging_embed[0]).squeeze(-1)

        targets = torch.where(
            torch.sigmoid(logits) > self.class_threshold.to(image.device),
            torch.tensor(1.0).to(image.device),
            torch.zeros(self.num_class).to(image.device))

        tag = targets.cpu().numpy()
        tags = []
        for b in range(bs):
            index = np.argwhere(tag[b] == 1)
            token = tag_list[index].squeeze(axis=1)
            tags.append(token.tolist())

        return tags[0]
