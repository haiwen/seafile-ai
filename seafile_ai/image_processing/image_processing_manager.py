from seafile_ai.image_processing.ocr import OCR


class ImageProcessingManager(object):
    def __init__(self, app):
        self.app = app
        self.ocr = OCR(app)

    def get_box_and_text(self, repo_id, file_path, obj_id):
        return self.ocr.get_box_and_text(repo_id, file_path, obj_id)
