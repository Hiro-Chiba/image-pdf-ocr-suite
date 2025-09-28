# Image PDF OCR Suite

画像ベースのPDFをOCR処理し、検索可能なPDFを生成したり、テキストを抽出したりできるPythonアプリケーションです。Tkinterを用いたデスクトップUIと、既存のCLIスクリプトのみで構成されています。

## 主な機能

- 画像ベースPDFを検索可能なPDFへ変換
- 画像ベースPDFからテキストを抽出してテキストファイルとして保存
- GUI（Tkinter）またはCLIから処理を実行可能

## ディレクトリ構成

```
image-pdf-ocr-suite/
├── image_pdf_ocr/              # OCRロジックをまとめたPythonモジュール
├── ocr_desktop_app.py          # Tkinterデスクトップアプリ
├── convert_to_searchable_pdf.py# PDF変換用CLI
├── extract_text_from_pdf.py    # テキスト抽出用CLI
└── requirements.txt
```

## 前提条件

- Python 3.10 以上
- Tesseract-OCR（日本語データを含む）
  - [UB Mannheim版インストーラー](https://github.com/UB-Mannheim/tesseract/wiki)が便利です。
  - インストール時に `Additional language data` → `Japanese` を選択し、可能であればシステムPATHへ追加してください。
  - もしコマンドラインから `tesseract -v` が実行できない場合は、環境変数 `TESSERACT_CMD` または `TESSERACT_PATH` に `tesseract.exe`（Windows）や `tesseract` バイナリ（macOS/Linux）のパスを設定してください。

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate  # Windowsでは .venv\\Scripts\\activate
pip install -r requirements.txt
```

## Tkinterデスクトップアプリの利用方法

1. `python ocr_desktop_app.py` を実行します。
2. 「入力PDF」でOCR対象のPDFを選択します。
3. 変換後PDFの保存先や抽出テキストの保存先を必要に応じて指定します（初期値は自動生成されます）。
4. 「検索可能PDFを作成」または「テキストを抽出」ボタンを押すと処理が開始されます。
5. 下部のログペインに進捗やエラーが表示され、処理完了時はダイアログでも通知されます。

## CLIスクリプトの利用

### 検索可能PDFの作成

```bash
python convert_to_searchable_pdf.py --input_path "入力PDFのパス" --output_path "出力PDFのパス"
```

### テキストの抽出

```bash
python extract_text_from_pdf.py --pdf_path "入力PDFのパス" --output_path "保存するテキストファイルのパス"
```

## トラブルシューティング

- `Tesseract-OCRが見つかりません。インストールとPATH設定を確認してください。`
  - Tesseract本体が未インストール、またはインストール済みでもPATHに登録されていない場合に発生します。
  - コマンドラインから `tesseract -v` が正常に実行できるか確認してください。
  - インストール先が標準パス以外の場合は、環境変数 `TESSERACT_CMD`（または `TESSERACT_PATH`）に実行ファイルのパスを設定してください。GUI/CLIいずれの処理でもこの設定が利用されます。

## ライセンス

本プロジェクトは [MIT License](LICENSE) の下で提供されます。
