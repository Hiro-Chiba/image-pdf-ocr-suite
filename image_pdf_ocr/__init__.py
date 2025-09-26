"""画像PDFを検索可能なPDFに変換するためのユーティリティモジュール。"""

from .ocr import create_searchable_pdf, find_and_set_tesseract_path

__all__ = ["create_searchable_pdf", "find_and_set_tesseract_path"]
