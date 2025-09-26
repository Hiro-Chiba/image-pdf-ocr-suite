import argparse
from pathlib import Path

from image_pdf_ocr import OCRConversionError, create_searchable_pdf


def main() -> None:
    parser = argparse.ArgumentParser(
        description="画像PDFをテキスト検索可能なPDFに変換します。",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--input_path",
        type=Path,
        required=True,
        help='入力する画像PDFのパス。\n例: "C:/scans/document.pdf"',
    )
    parser.add_argument(
        "--output_path",
        type=Path,
        required=True,
        help='出力する検索可能PDFのパス。\n例: "C:/scans/document_searchable.pdf"',
    )

    args = parser.parse_args()

    try:
        create_searchable_pdf(args.input_path, args.output_path)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    except OCRConversionError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
