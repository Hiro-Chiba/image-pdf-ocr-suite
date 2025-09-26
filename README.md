# Image PDF OCR Suite

画像ベースのPDFにOCR処理を施し、検索可能なPDFへ変換するためのフルスタックアプリケーションです。FastAPIバックエンドでOCR変換を行い、Reactフロントエンドからアップロード・プレビュー・ダウンロードをシームレスに実行できます。

## 機能概要

- 画像ベースPDFをアップロードしてOCR変換
- 変換後PDFのブラウザプレビューとダウンロード
- FastAPIによるREST API `/convert`
- React（Vite）による単一ページUI

## システム構成

```
image-pdf-ocr-suite/
├── backend/          # FastAPI アプリケーション
├── frontend/         # React + Vite フロントエンド
├── image_pdf_ocr/    # OCRロジックをまとめたPythonモジュール
├── convert_to_searchable_pdf.py  # CLIスクリプト
├── extract_text_from_pdf.py      # 既存のテキスト抽出スクリプト
└── requirements.txt
```

## 前提条件

- Python 3.10 以上
- Node.js 18 以上
- Tesseract-OCR（日本語データを含む）
  - [UB Mannheim版インストーラー](https://github.com/UB-Mannheim/tesseract/wiki)を利用すると便利です。
  - インストール時に `Additional language data` → `Japanese` を選択し、可能ならシステムPATHへ追加してください。

## セットアップ手順

### 1. Python依存関係のインストール

```bash
python -m venv .venv
source .venv/bin/activate  # Windowsでは .venv\\Scripts\\activate
pip install -r requirements.txt
```

### 2. バックエンドの起動

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- `http://localhost:8000/docs` にアクセスするとAPIドキュメント（Swagger UI）を確認できます。

### 3. フロントエンドのセットアップ・起動

別ターミナルで以下を実行します。

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

ブラウザで `http://localhost:5173` を開くとUIが表示されます。フロントエンドからPDFをアップロードすると、バックエンドの `/convert` APIを通じてOCR変換が行われ、結果PDFのプレビューとダウンロードが可能です。

### 環境変数

バックエンドのURLを変更する場合は、`frontend/.env` に以下のように設定できます。

```
VITE_API_URL=http://localhost:8000/convert
```

## CLIスクリプトとしての利用

GUIではなくコマンドラインで変換したい場合は、従来通り `convert_to_searchable_pdf.py` を使用できます。

```bash
python convert_to_searchable_pdf.py --input_path "入力PDFのパス" --output_path "出力PDFのパス"
```

## 開発用スクリプト

- バックエンドAPIの起動: `uvicorn app.main:app --reload`
- フロントエンドのビルド: `npm run build`
- フロントエンドのLint: `npm run lint`

## ライセンス

本プロジェクトは [MIT License](LICENSE) の下で提供されます。
