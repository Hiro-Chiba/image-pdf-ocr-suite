# 画像PDFテキスト処理ツール

画像ベースのPDFからテキストを抽出し、「検索可能なPDF」または「テキストファイル」を生成するツール群です。

スキャンした書類や、写真から作成したPDFなど、テキスト情報を含まないPDFを、ChatGPTなどのAIが直接読み取れる形式に変換したり、テキストとして保存したりできます。

## 事前準備

このスクリプトを使用するには、以下の2つのツールを事前にインストールする必要があります。

### 1. Python

- Python 3.x がインストールされている必要があります。

### 2. Tesseract-OCR

OCRを実行するためのエンジンです。

1.  **インストーラーのダウンロード**:
    - [こちらのページ](https://github.com/UB-Mannheim/tesseract/wiki)から、ご自身の環境に合ったインストーラー（`tesseract-ocr-w64-setup-*.exe`など）をダウンロードします。

2.  **インストール**:
    - ダウンロードしたインストーラーを実行します。
    - **【重要】** インストール中にコンポーネントを選択する画面（`Choose Components`）で、`Additional language data` を展開し、**`Japanese`** にチェックを入れてください。
    - ![Tesseract-Language-Select](https://i.imgur.com/g60333v.png)
    - また、可能であれば**「Add Tesseract to system PATH」** のような、システムパスにTesseractを追加するオプションを有効にしてください。

## スクリプトのセットアップ

1.  **Pythonライブラリのインストール**:
    - ターミナル（コマンドプロンプト）で以下のコマンドを実行し、必要なライブラリをインストールします。
      ```bash
      python -m pip install pytesseract Pillow PyMuPDF pandas
      ```

## 使い方

目的に応じて2つのスクリプトを使い分けます。

### A) 検索可能なPDFを作成する（推奨）

元のPDFの見た目はそのままに、テキスト選択や検索が可能な新しいPDFを作成します。**ChatGPTなどでの利用に最適です。**

- **スクリプト:** `convert_to_searchable_pdf.py`
- **コマンド:**
    ```bash
    python convert_to_searchable_pdf.py --input_path "入力PDFのフルパス" --output_path "出力PDFのフルパス"
    ```
- **コマンド例:**
    ```bash
    python convert_to_searchable_pdf.py --input_path "C:\scans\image_doc.pdf" --output_path "C:\scans\searchable_doc.pdf"
    ```

### B) テキストファイルとして抽出する

PDFからテキスト情報のみを抽出し、`.txt`ファイルとして保存します。

- **スクリプト:** `extract_text_from_pdf.py`
- **コマンド:**
    ```bash
    python extract_text_from_pdf.py --pdf_path "入力PDFのフルパス" --output_path "出力テキストのフルパス"
    ```
- **コマンド例:**
    ```bash
    python extract_text_from_pdf.py --pdf_path "C:\scans\image_doc.pdf" --output_path "C:\scans\extracted_text.txt"
    ```

## 注意点

- **OCRの精度**: PDF内の画像の品質、文字のフォント、レイアウトの複雑さによって、テキストの認識精度は変わります。100%完璧に抽出できるわけではありません。
- **Tesseract-OCRが見つからないエラー**:
  - スクリプトはTesseract-OCRを自動で検出しようとしますが、見つからない場合はエラーメッセージが表示されます。
  - その際は、Tesseract-OCRが正しくインストールされているか（特に日本語パック）、システムのPATHに登録されているかをご確認ください。