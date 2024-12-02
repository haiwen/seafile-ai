import logging
import os
from io import BytesIO

import torch
from PIL import Image

from image_tags.models.tag2text import Tag2Text
from image_tags.models.utils import load_checkpoint, get_image_by_token, get_transform

logger = logging.getLogger(__name__)


class ImageTagsManager:

    def __init__(self, model_dir):
        self.transform = get_transform()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = Tag2Text(model_dir)
        self.model = load_checkpoint(self.model, model_dir).to(self.device)
        self.model.eval()

    def image_tags(self, path, download_token):
        file_name = os.path.basename(path.rstrip('/'))
        content = get_image_by_token(download_token, file_name)
        if not content:
            return None

        image = self.transform(Image.open(BytesIO(content))).unsqueeze(0).to(self.device)
        return self.model.predict(image)
