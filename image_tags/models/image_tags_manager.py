import logging
import os
from io import BytesIO

import torch
from PIL import Image

from image_tags.models.tag2text import Tag2Text
from image_tags.models.ram import RAM
from image_tags.models.utils import load_checkpoint, get_image_by_token, get_transform

logger = logging.getLogger(__name__)


class ImageTagsManager:

    def __init__(self, model_dir, model_type):
        self.transform = get_transform()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        if model_type == 'tag2text':
            self.model = Tag2Text(model_dir)
            self.model = load_checkpoint(self.model, os.path.join(model_dir, 'tag2text_swin_14m_only_tags.pth')).to(self.device)
        elif model_type == 'ram':
            self.model = RAM(model_dir)
            self.model = load_checkpoint(self.model, os.path.join(model_dir, 'ram_swin_14m_only_tags.pth')).to(self.device)
        else:
            raise NotImplementedError
        self.model.eval()

    def image_tags(self, path, download_token, lang):
        file_name = os.path.basename(path.rstrip('/'))
        content = get_image_by_token(download_token, file_name)
        if not content:
            return None

        image = self.transform(Image.open(BytesIO(content))).unsqueeze(0).to(self.device)
        return self.model.predict(image, lang)
