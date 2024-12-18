import torch


class Resize(torch.nn.Module):
    def __init__(self, size, interpolation=2, max_size=None):
        super().__init__()
        self.size = size
        self.max_size = max_size

        self.interpolation = interpolation

    def forward(self, img):
        return resize(img, self.size, self.interpolation)

    def __repr__(self) -> str:
        detail = f"(size={self.size}, interpolation={self.interpolation.value}, max_size={self.max_size}, antialias={self.antialias})"
        return f"{self.__class__.__name__}{detail}"


def resize(
    img,
    size,
    interpolation=2,
):
    image_height, image_width = img.size
    output_size = size

    if [image_height, image_width] == output_size:
        return img

    return img.resize(tuple(output_size[::-1]), interpolation)
