import os
import logging

import pypdf

from io import BytesIO

from pdf2image import convert_from_bytes

from seafile_ai.utils import upload_file
from seafile_ai.pdf_manager.convert_to_dual_layer import OutputPDFLayered


logger = logging.getLogger(__name__)


class PDFManager:
    def __init__(self, app):
        self.app = app

        OutputPDFLayered.register_all_fonts()

    @staticmethod
    def read_pdf(b_pdf):
        return pypdf.PdfReader(BytesIO(b_pdf))

    @staticmethod
    def has_text_layer(pdf_reader):
        for page in pdf_reader.pages:
            if page.extract_text():
                return True
        return False

    @staticmethod
    def get_bytes_img(image, format='png'):
        bytes_io = BytesIO()
        image.save(bytes_io, format=format)
        return bytes_io.getvalue()

    def gen_dual_layer_pdf(self, task_id, path, b_pdf, upload_token):
        pdf_reader = self.read_pdf(b_pdf)
        pdf_processor = OutputPDFLayered()
        total_pages = len(pdf_reader.pages)
        progress_interval = max(total_pages // 5, 1)
        for page_index, page in enumerate(pdf_reader.pages):
            byte_pngs, scale = self.convert_page_to_img(
                b_pdf, page, page_index, page_index, min_resolution=1080
            )
            params = {'img': byte_pngs[0]}
            ocr_res = self.app.ocr_api.ocr(params)['ocr_result']
            pdf_processor.process_page(page, ocr_res, scale)
            if (page_index + 1) % progress_interval == 0 or page_index == total_pages - 1:
                logger.info(f'Processing progress: {page_index + 1}/{total_pages} pages completed. task_id: {task_id}')
        pdf_binary_stream = BytesIO()
        pdf_processor.writer.write(pdf_binary_stream)
        pdf_binary_stream.seek(0)

        # Upload file
        upload_file(
            upload_token,
            pdf_binary_stream,
            os.path.dirname(path),
            '[OCR]' + os.path.basename(path),
        )

    def convert_page_to_img(self, pdf, page, s_index, e_index, min_resolution=None):
        """Return (bytes images list, img scale)"""
        media_box = page.mediabox
        width_pt = float(media_box.width)
        height_pt = float(media_box.height)
        min_dimension = min(width_pt, height_pt)
        scale = None
        if min_resolution:
            if min_dimension < min_resolution:
                zoom = min_resolution / max(min_dimension, 1)
            else:
                zoom = 1
            scale = 1 / zoom
            # 72 is the PDF native resolution.
            dpi = 72 * zoom

            # Pypdf does not have a built-in method to convert PDF pages to images.
            # Use pdf2image
            images = convert_from_bytes(
                pdf, first_page=s_index + 1, last_page=e_index + 1, dpi=dpi
            )
        else:
            images = convert_from_bytes(
                pdf,
                first_page=s_index + 1,
                last_page=e_index + 1,
            )

        return [self.get_bytes_img(img) for img in images], scale
