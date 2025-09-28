"""画像ベースPDFからテキストを抽出するCLIスクリプト。"""

from __future__ import annotations

import argparse
from pathlib import Path

from image_pdf_ocr import OCRConversionError, extract_text_to_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="画像ベースのPDFからOCRでテキストを抽出します。",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--pdf_path",
        type=Path,
        required=True,
        help='入力するPDFファイルのパス。\n例: "C:/Users/YourUser/Documents/scan.pdf"',
    )
    parser.add_argument(
        "--output_path",
        type=Path,
        required=True,
        help='抽出したテキストを保存するパス。\n例: "C:/Users/YourUser/Documents/output.txt"',
    )

    args = parser.parse_args()

    try:
        extract_text_to_file(args.pdf_path, args.output_path)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    except OCRConversionError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
