"""OCR機能を提供するモジュール。"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Union

import fitz  # type: ignore
import pytesseract
from PIL import Image


class OCRConversionError(RuntimeError):
    """OCR変換処理で発生した例外。"""


def find_and_set_tesseract_path() -> bool:
    """Windows環境でTesseractのパスを推測して設定する。"""
    path_64 = Path(r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
    path_32 = Path(r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe")

    if path_64.exists():
        pytesseract.pytesseract.tesseract_cmd = str(path_64)
        return True
    if path_32.exists():
        pytesseract.pytesseract.tesseract_cmd = str(path_32)
        return True

    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        return False
    return True


def create_searchable_pdf(
    input_path: Union[str, os.PathLike], output_path: Union[str, os.PathLike]
) -> None:
    """画像PDFをOCRして検索可能なPDFを生成する。"""
    if not find_and_set_tesseract_path():
        raise OCRConversionError("Tesseract-OCRが見つかりません。インストールとPATH設定を確認してください。")

    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_path}")

    try:
        input_doc = fitz.open(input_path)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - PyMuPDF例外
        raise OCRConversionError(f"PDFファイルを開けませんでした: {exc}") from exc

    output_doc = fitz.open()

    try:
        for page in input_doc:
            pix = page.get_pixmap(dpi=300)
            with Image.open(io.BytesIO(pix.tobytes("png"))) as img:
                ocr_data = pytesseract.image_to_data(
                    img, lang="jpn", output_type=pytesseract.Output.DATAFRAME
                )
            ocr_data = ocr_data[ocr_data.conf > 50]

            new_page = output_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, pixmap=pix)

            for _, row in ocr_data.iterrows():
                text = str(row.get("text", "")).strip()
                if not text:
                    continue
                x = row.get("left", 0)
                y = row.get("top", 0)
                h = row.get("height", 0)
                try:
                    new_page.insert_text((x, y + h), text, fontname="cjk", fontsize=h * 0.8, render_mode=3)
                except RuntimeError:
                    # PyMuPDFのフォント描画で稀に失敗するケースがあるため無視
                    continue
    except Exception as exc:
        raise OCRConversionError(f"ページ処理中に問題が発生しました: {exc}") from exc
    finally:
        input_doc.close()

    try:
        output_doc.save(output_path, garbage=4, deflate=True, clean=True)
    except Exception as exc:  # pragma: no cover - save時のPyMuPDF例外
        raise OCRConversionError(f"PDFを保存できませんでした: {exc}") from exc
    finally:
        output_doc.close()


def extract_text_from_image_pdf(input_path: Union[str, os.PathLike]) -> str:
    """画像ベースのPDFからOCRでテキストを抽出して返す。"""

    if not find_and_set_tesseract_path():
        raise OCRConversionError(
            "Tesseract-OCRが見つかりません。インストールとPATH設定を確認してください。"
        )

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_path}")

    try:
        document = fitz.open(input_path)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - PyMuPDF例外
        raise OCRConversionError(f"PDFファイルを開けませんでした: {exc}") from exc

    texts: list[str] = []
    try:
        for index, page in enumerate(document, start=1):
            pix = page.get_pixmap(dpi=300)
            with Image.open(io.BytesIO(pix.tobytes("png"))) as image:
                page_text = pytesseract.image_to_string(image, lang="jpn")
            texts.append(f"--- ページ {index} ---\n{page_text.strip()}\n")
    except Exception as exc:
        raise OCRConversionError(f"テキスト抽出中に問題が発生しました: {exc}") from exc
    finally:
        document.close()

    return "\n".join(texts).strip() + "\n"


def extract_text_to_file(
    input_path: Union[str, os.PathLike], output_path: Union[str, os.PathLike]
) -> None:
    """画像PDFから抽出したテキストをファイルに保存する。"""

    text = extract_text_from_image_pdf(input_path)
    output_path = Path(output_path)
    output_path.write_text(text, encoding="utf-8")
