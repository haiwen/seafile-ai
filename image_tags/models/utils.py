import json
import logging
import os

import requests
import torch
import math

from urllib.parse import quote as urlquote

from torch import nn
from transformers import BertTokenizer
from torchvision.transforms import Normalize, Compose, Resize, ToTensor

from image_tags.config import FILE_SERVER

logger = logging.getLogger(__name__)


def read_json(rpath):
    with open(rpath, 'r') as f:
        return json.load(f)


class GroupWiseLinear(nn.Module):
    # could be changed to:
    # output = torch.einsum('ijk,zjk->ij', x, self.W)
    # or output = torch.einsum('ijk,jk->ij', x, self.W[0])
    def __init__(self, num_class, hidden_dim, bias=True):
        super().__init__()
        self.num_class = num_class
        self.hidden_dim = hidden_dim
        self.bias = bias

        self.W = nn.Parameter(torch.Tensor(1, num_class, hidden_dim))
        if bias:
            self.b = nn.Parameter(torch.Tensor(1, num_class))
        self.reset_parameters()

    def reset_parameters(self):
        stdv = 1. / math.sqrt(self.W.size(2))
        for i in range(self.num_class):
            self.W[0][i].data.uniform_(-stdv, stdv)
        if self.bias:
            for i in range(self.num_class):
                self.b[0][i].data.uniform_(-stdv, stdv)

    def forward(self, x):
        # x: B,K,d
        x = (self.W * x).sum(-1)
        if self.bias:
            x = x + self.b
        return x


def init_tokenizer(tokenizer_path):
    tokenizer = BertTokenizer.from_pretrained(tokenizer_path)
    tokenizer.add_special_tokens({'bos_token': '[DEC]'})
    tokenizer.add_special_tokens({'additional_special_tokens': ['[ENC]']})
    tokenizer.enc_token_id = tokenizer.additional_special_tokens_ids[0]
    return tokenizer


def load_checkpoint(model, model_dir):
    checkpoint_path = os.path.join(model_dir, 'tag2text_swin_14m_only_tags.pth')
    state_dict = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
    model.load_state_dict(state_dict, strict=False)
    logger.info('load checkpoint from %s' % checkpoint_path)
    return model


def convert_to_rgb(image):
    return image.convert("RGB")


def get_transform(image_size=384):
    return Compose([
        convert_to_rgb,
        Resize((image_size, image_size)),
        ToTensor(),
        Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])


def gen_file_get_url(token, filename):
    return '%s/files/%s/%s' % (FILE_SERVER, token, urlquote(filename))


def get_image_by_token(token, filename):
    url = gen_file_get_url(token, filename)
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise ConnectionError(response.status_code, response.text)

    return response.content
