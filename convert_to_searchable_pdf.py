
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import argparse
import os
import sys
import pandas as pd

def find_and_set_tesseract_path():
    """
    Windows環境でTesseract-OCRのパスを自動検出し、設定する。
    """
    path_64 = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    path_32 = r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'

    if os.path.exists(path_64):
        pytesseract.pytesseract.tesseract_cmd = path_64
        return True
    elif os.path.exists(path_32):
        pytesseract.pytesseract.tesseract_cmd = path_32
        return True
    try:
        pytesseract.get_tesseract_version()
        return True
    except pytesseract.TesseractNotFoundError:
        return False

def create_searchable_pdf(input_path, output_path):
    """
    画像ベースのPDFを、テキスト検索可能なPDFに変換する。
    """
    if not find_and_set_tesseract_path():
        print("--- エラー ---\nTesseract-OCRが見つかりませんでした。\nインストールとPATH設定を確認してください。", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(input_path):
        print(f"エラー: 入力ファイルが見つかりません: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        input_doc = fitz.open(input_path)
        output_doc = fitz.open()  # 新しい空のPDFを作成
    except Exception as e:
        print(f"エラー: PDFファイルを開けませんでした: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"変換処理を開始します... (全{len(input_doc)}ページ)")

    try:
        for i, page in enumerate(input_doc):
            print(f" - {i + 1}ページ目を処理中...")
            
            # 1. ページを画像化
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes()))

            # 2. OCRでテキストと位置情報を取得
            ocr_data = pytesseract.image_to_data(img, lang='jpn', output_type=pytesseract.Output.DATAFRAME)
            ocr_data = ocr_data[ocr_data.conf > 50] # 信頼度が50%以上の単語のみ対象

            # 3. 新しいPDFにページを追加し、背景として元の画像を設定
            new_page = output_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, pixmap=pix)

            # 4. 取得したテキストを「見えない状態」で配置
            for _, row in ocr_data.iterrows():
                if str(row['text']).strip():
                    x, y, w, h = row['left'], row['top'], row['width'], row['height']
                    # render_mode=3でテキストを非表示にする
                    new_page.insert_text((x, y + h), row['text'], fontname="cjk", fontsize=h*0.8, render_mode=3)

    except Exception as e:
        print(f"\nエラー: ページ{i+1}の処理中に問題が発生しました。", file=sys.stderr)
        print(f"詳細: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        input_doc.close()

    try:
        # 最適化して保存
        output_doc.save(output_path, garbage=4, deflate=True, clean=True)
        print(f"\n処理が完了しました。")
        print(f"検索可能なPDFを '{output_path}' に保存しました。")
    except Exception as e:
        print(f"\nエラー: PDFを保存できませんでした: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        output_doc.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='画像PDFをテキスト検索可能なPDFに変換します。',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--input_path', 
        type=str, 
        required=True, 
        help='入力する画像PDFのパス。\n例: "C:\\scans\\document.pdf"'
    )
    parser.add_argument(
        '--output_path', 
        type=str, 
        required=True, 
        help='出力する検索可能PDFのパス。\n例: "C:\\scans\\document_searchable.pdf"'
    )

    args = parser.parse_args()
    create_searchable_pdf(args.input_path, args.output_path)
