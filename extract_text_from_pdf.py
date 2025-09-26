import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import argparse
import os
import sys

def find_and_set_tesseract_path():
    """
    Windows環境でTesseract-OCRのパスを自動検出し、設定する。
    """
    # 64-bit版の一般的なインストール先
    path_64 = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    # 32-bit版の一般的なインストール先
    path_32 = r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'

    if os.path.exists(path_64):
        print(f"Tesseract-OCRを検出しました: {path_64}")
        pytesseract.pytesseract.tesseract_cmd = path_64
        return True
    elif os.path.exists(path_32):
        print(f"Tesseract-OCRを検出しました: {path_32}")
        pytesseract.pytesseract.tesseract_cmd = path_32
        return True
    
    # 環境変数PATHから探す
    try:
        # この呼び出し自体がTesseractを見つけられない場合にエラーを出す
        pytesseract.get_tesseract_version()
        print("環境変数PATHからTesseract-OCRを検出しました。")
        return True
    except pytesseract.TesseractNotFoundError:
        return False

def extract_text_from_image_pdf(pdf_path, output_path):
    """
    画像ベースのPDFからOCRを使ってテキストを抽出し、ファイルに保存する。
    """
    if not find_and_set_tesseract_path():
        print("\n--- エラー ---", file=sys.stderr)
        print("Tesseract-OCRが見つかりませんでした。", file=sys.stderr)
        print("プログラムを実行するには、Tesseract-OCRをインストールする必要があります。", file=sys.stderr)
        print("インストール時に「Add Tesseract to system PATH」を有効にするか、", file=sys.stderr)
        print(f"このスクリプト({__file__})内のパスを手動で設定してください。", file=sys.stderr)
        print("----------------", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(pdf_path):
        print(f"エラー: 指定されたPDFファイルが見つかりません: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"エラー: PDFファイルを開けませんでした: {pdf_path}", file=sys.stderr)
        print(f"詳細: {e}", file=sys.stderr)
        sys.exit(1)
        
    full_text = ""
    print(f"\nPDFからテキストを抽出中... (全{len(doc)}ページ)")

    try:
        for i, page in enumerate(doc):
            print(f" - {i + 1}ページ目を処理中...")
            
            # ページを高解像度画像(PNG)に変換
            pix = page.get_pixmap(dpi=300)
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))

            # OCRで画像からテキストを抽出（日本語を指定）
            text = pytesseract.image_to_string(image, lang='jpn')
            full_text += f"--- ページ {i + 1} ---\n"
            full_text += text.strip() + "\n\n"

    except Exception as e:
        print(f"\nエラー: ページ{i+1}の処理中に問題が発生しました。", file=sys.stderr)
        print(f"詳細: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if 'doc' in locals() and doc:
            doc.close()

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_text)
        print(f"\n処理が完了しました。")
        print(f"抽出したテキストを '{output_path}' に保存しました。")
    except Exception as e:
        print(f"\nエラー: 抽出したテキストをファイルに保存できませんでした: {output_path}", file=sys.stderr)
        print(f"詳細: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='画像ベースのPDFからOCRでテキストを抽出します。',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--pdf_path', 
        type=str, 
        required=True, 
        help='入力するPDFファイルのパス。\n例: "C:\Users\YourUser\Documents\scan.pdf"'
    )
    parser.add_argument(
        '--output_path', 
        type=str, 
        required=True, 
        help='出力するテキストファイルのパス。\n例: "C:\Users\YourUser\Documents\output.txt"'
    )

    args = parser.parse_args()
    extract_text_from_image_pdf(args.pdf_path, args.output_path)