import logging

from io import BytesIO
from functools import lru_cache

from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from pypdf import PdfReader, PdfWriter


logger = logging.getLogger(__name__)


@lru_cache(maxsize=3)
def is_font_registered(font_name):
    return font_name in pdfmetrics.getRegisteredFontNames()


class OutputPDFLayered:
    def __init__(self):
        self.writer = PdfWriter()

    @staticmethod
    def register_all_fonts():
        from seafile_ai import config

        if hasattr(config, 'FONTS'):
            try:
                for font_info in config.FONTS:
                    name = font_info.get('name')
                    path = font_info.get('path')
                    if name and path:
                        pdfmetrics.registerFont(TTFont(name, path))
            except Exception as e:
                logger.warning(f'Failed to register font, error: {e}')

    def calculate_font_size(self, text, box_width, box_height):
        """Calculate the font size to fit the given width and height"""
        if box_height > box_width:  # Vertical to horizontal calculation
            box_width, box_height = box_height, box_width
        font_size = round(box_height)

        min_size = 3  # Lower limit of font size

        font_name = 'SourceHanSansCN'
        if is_font_registered(font_name) is False:
            # Built-in font in reportlab
            font_name = 'Helvetica'
        get_text_length = lambda text, size: pdfmetrics.stringWidth(
            text, font_name, fontSize=size
        )

        while get_text_length(text, font_size) > box_width and font_size >= min_size:
            font_size -= 1  # Decrease font size
        while get_text_length(text, font_size) < box_width:
            font_size += 1  # Increase font size
        while get_text_length(text, font_size) > box_width and font_size >= min_size:
            font_size -= 0.1  # Precise adjustment

        return font_size

    def insert_text(self, text, box, canvas):
        x0, y0 = box[0]
        x2, y2 = box[2]
        width = x2 - x0
        height = y2 - y0
        font_size = self.calculate_font_size(text, width, height)

        canvas.setFillColorRGB(0, 0, 0, alpha=0)  # Set transparency
        font_name = 'SourceHanSansCN'
        if is_font_registered(font_name) is False:
            # Built-in font in reportlab
            font_name = 'Helvetica'
        canvas.setFont(font_name, font_size)  # Set font and size
        canvas.drawString(x0, y2, text)  # Draw text

    def process_page(self, page, ocr_res, scale=1):
        # Create an in-memory PDF for the text layer
        packet = BytesIO()
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        can = canvas.Canvas(
            packet, pagesize=(width, height)
        )  # Dynamically set page size
        for tb in ocr_res:
            if not tb["text"][0]:
                continue
            # Translate all text block coordinates from the image
            # relative coordinate system to the page absolute coordinate system.
            for bi in range(4):
                tb["box"][bi][0] = tb["box"][bi][0] * scale
                # The default coordinate origin is at the lower left corner in reportlab
                tb["box"][bi][1] = height - tb["box"][bi][1] * scale

            self.insert_text(tb["text"][0], tb["box"], can)

        # Close the current page
        can.showPage()
        can.save()
        # Read the text layer as a PDF
        packet.seek(0)
        text_layer_pdf = PdfReader(packet)
        text_layer_page = text_layer_pdf.pages[0]

        # Merge the text layer with the original page
        page.merge_page(text_layer_page)
        # Add the merged page to the writer
        self.writer.add_page(page)
