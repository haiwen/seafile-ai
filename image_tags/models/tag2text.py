import numpy as np
import os
from torch import nn
import torch

from .bert import BertConfig, BertModel
from .swin_transformer import SwinTransformer

from .utils import read_json, init_tokenizer, GroupWiseLinear


class Tag2Text(nn.Module):

    def __init__(self, model_dir, threshold=0.68, delete_tag_index=None):
        r""" Tag2Text inference module, both captioning and tagging are included.
        Tag2Text is an efficient and controllable vision-language pre-training framework.
        Described in the paper "Tag2Text: Guiding Vision-Language Model via Image Tagging" https://arxiv.org/abs/2303.05657

        Args:
            threshold (int): tagging threshold
            delete_tag_index (list): delete some tags that may disturb captioning
        """
        super().__init__()
        if delete_tag_index is None:
            delete_tag_index = [127, 2961, 3351, 3265, 3338, 3355, 3359]
        vision_config_path = os.path.join(model_dir, 'config_swinB_384.json')
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
            use_checkpoint=False
        )

        # create tokenzier
        self.tokenizer = init_tokenizer(os.path.join(model_dir, 'tokenizer'))

        # delete some tags that may disturb captioning
        # 127: "quarter"; 2961: "back"; 3351: "two"; 3265: "three"; 3338: "four"; 3355: "five"; 3359: "one"
        self.delete_tag_index = delete_tag_index

        # load tag list
        self.tag_list = self.load_tag_list(os.path.join(model_dir, 'tag_list.txt'))

        # create image-tag recognition decoder
        self.threshold = threshold
        self.num_class = len(self.tag_list)
        q2l_config = BertConfig.from_json_file(os.path.join(model_dir, 'q2l_config.json'))
        q2l_config.encoder_width = vision_width
        self.tagging_head = BertModel(config=q2l_config,
                                      add_pooling_layer=False)
        self.tagging_head.resize_token_embeddings(len(self.tokenizer))
        self.label_embed = nn.Embedding(self.num_class, q2l_config.hidden_size)
        self.fc = GroupWiseLinear(self.num_class,
                                  q2l_config.hidden_size,
                                  bias=True)
        self.del_selfattention()

        # adjust thresholds for some tags
        # default threshold: 0.68
        # 2701: "person"; 2828: "man"; 1167: "woman"
        tag_thrshold = {2701: 0.7, 2828: 0.7, 1167: 0.7}
        self.class_threshold = torch.ones(self.num_class) * self.threshold
        for key, value in tag_thrshold.items():
            self.class_threshold[key] = value

    def load_tag_list(self, tag_list_file):
        with open(tag_list_file, 'r') as f:
            tag_list = f.read().splitlines()
        tag_list = np.array(tag_list)
        return tag_list

    # delete self-attention layer of image-tag recognition decoder to reduce computation, follower Query2Label
    def del_selfattention(self):
        del self.tagging_head.embeddings
        for layer in self.tagging_head.encoder.layer:
            del layer.attention

    def predict(self, image):

        image_embeds = self.visual_encoder(image)
        image_atts = torch.ones(image_embeds.size()[:-1],
                                dtype=torch.long).to(image.device)

        bs = image_embeds.shape[0]
        label_embed = self.label_embed.weight.unsqueeze(0).repeat(bs, 1, 1)
        tagging_embed = self.tagging_head(
            encoder_embeds=label_embed,
            encoder_hidden_states=image_embeds,
            encoder_attention_mask=image_atts,
            return_dict=False,
            mode='tagging',
        )

        logits = self.fc(tagging_embed[0])

        targets = torch.where(
            torch.sigmoid(logits) > self.class_threshold.to(image.device),
            torch.tensor(1.0).to(image.device),
            torch.zeros(self.num_class).to(image.device))

        tag = targets.cpu().numpy()

        # delete some tags that may disturb captioning
        tag[:, self.delete_tag_index] = 0

        tags = []
        for b in range(bs):
            index = np.argwhere(tag[b] == 1)
            token = self.tag_list[index].squeeze(axis=1)
            tags.append(token.tolist())

        return tags[0]
