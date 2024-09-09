import open_clip
import torch


class CLIPModel:
    def __init__(self, model_path):
        self.model, _, self.transform = open_clip.create_model_and_transforms(
            'ViT-B-32',
            'openai',
            device='cuda' if torch.cuda.is_available() else 'cpu',
            cache_dir=model_path,
        )
        self.model.eval()

    def embedding(self, image):
        image = self.transform(image.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            image_features = self.model.encode_image(image)
            image_features /= image_features.norm(dim=-1, keepdim=True)

        return image_features
