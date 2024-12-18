from enum import Enum

import torch


class InterpolationMode(Enum):
    """Interpolation modes
    Available interpolation methods are ``nearest``, ``nearest-exact``, ``bilinear``, ``bicubic``, ``box``, ``hamming``,
    and ``lanczos``.
    """

    NEAREST = "nearest"
    NEAREST_EXACT = "nearest-exact"
    BILINEAR = "bilinear"
    BICUBIC = "bicubic"
    # For PIL compatibility
    BOX = "box"
    HAMMING = "hamming"
    LANCZOS = "lanczos"


def _interpolation_modes_from_int(i):
    inverse_modes_mapping = {
        0: InterpolationMode.NEAREST,
        2: InterpolationMode.BILINEAR,
        3: InterpolationMode.BICUBIC,
        4: InterpolationMode.BOX,
        5: InterpolationMode.HAMMING,
        1: InterpolationMode.LANCZOS,
    }
    return inverse_modes_mapping[i]


pil_modes_mapping = {
    InterpolationMode.NEAREST: 0,
    InterpolationMode.BILINEAR: 2,
    InterpolationMode.BICUBIC: 3,
    InterpolationMode.NEAREST_EXACT: 0,
    InterpolationMode.BOX: 4,
    InterpolationMode.HAMMING: 5,
    InterpolationMode.LANCZOS: 1,
}


class Resize(torch.nn.Module):
    def __init__(self, size, interpolation=InterpolationMode.BILINEAR, max_size=None):
        super().__init__()
        self.size = size
        self.max_size = max_size

        if isinstance(interpolation, int):
            interpolation = _interpolation_modes_from_int(interpolation)

        self.interpolation = interpolation

    def forward(self, img):
        """
        Args:
            img (PIL Image or Tensor): Image to be scaled.

        Returns:
            PIL Image or Tensor: Rescaled image.
        """
        return resize(img, self.size, self.interpolation, self.max_size)

    def __repr__(self) -> str:
        detail = f"(size={self.size}, interpolation={self.interpolation.value}, max_size={self.max_size}, antialias={self.antialias})"
        return f"{self.__class__.__name__}{detail}"


def get_dimensions(img):
    if hasattr(img, "getbands"):
        channels = len(img.getbands())
    else:
        channels = img.channels
    width, height = img.size
    return [channels, height, width]


def _compute_resized_output_size(
    image_size,
    size,
    max_size=None,
    allow_size_none=False,  # only True in v2
):
    h, w = image_size
    short, long = (w, h) if w <= h else (h, w)
    if size is None:
        if not allow_size_none:
            raise ValueError("This should never happen!!")
        if not isinstance(max_size, int):
            raise ValueError(f"max_size must be an integer when size is None, but got {max_size} instead.")
        new_short, new_long = int(max_size * short / long), max_size
        new_w, new_h = (new_short, new_long) if w <= h else (new_long, new_short)
    elif len(size) == 1:  # specified size only for the smallest edge
        requested_new_short = size if isinstance(size, int) else size[0]
        new_short, new_long = requested_new_short, int(requested_new_short * long / short)

        if max_size is not None:
            if max_size <= requested_new_short:
                raise ValueError(
                    f"max_size = {max_size} must be strictly greater than the requested "
                    f"size for the smaller edge size = {size}"
                )
            if new_long > max_size:
                new_short, new_long = int(max_size * new_short / new_long), max_size

        new_w, new_h = (new_short, new_long) if w <= h else (new_long, new_short)
    else:  # specified both h and w
        new_w, new_h = size[1], size[0]
    return [new_h, new_w]


def resize(
    img,
    size,
    interpolation=InterpolationMode.BILINEAR,
    max_size=None,
):
    if isinstance(interpolation, int):
        interpolation = _interpolation_modes_from_int(interpolation)

    _, image_height, image_width = get_dimensions(img)
    if isinstance(size, int):
        size = [size]
    output_size = _compute_resized_output_size((image_height, image_width), size, max_size)

    if [image_height, image_width] == output_size:
        return img

    pil_interpolation = pil_modes_mapping[interpolation]
    return img.resize(tuple(output_size[::-1]), pil_interpolation)
