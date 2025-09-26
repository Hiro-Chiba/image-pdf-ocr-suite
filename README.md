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

バックエンドのURLを変更する場合は、`frontend/.env` に以下のように設定できます。`.env` を直接編集せず、まずは同ディレクトリに用意した `.env.example` をコピーしてください。

```
cp frontend/.env.example frontend/.env
```

`frontend/.env` 内の `VITE_API_URL` を、デプロイ先のバックエンドURLに合わせて編集します。

```
VITE_API_URL=http://localhost:8000/convert
```

> **補足**: Vercel でホスティングする場合、フロントエンドから参照できる公開URLを `VITE_API_URL` に設定する必要があります。Vercel のプロジェクト設定で環境変数を追加すると、ビルド時に反映されます。

## Vercel へのデプロイ

Vercel ではフロントエンド（`frontend` ディレクトリ配下）を静的サイトとしてホスティングできます。リポジトリルートには `vercel.json` を配置しており、以下の設定で Vite ビルド成果物を公開します。

- ビルドターゲット: `frontend/package.json` を `@vercel/static-build` で処理
- インストールコマンド: `npm install --prefix frontend`
- ビルドコマンド: `npm run build --prefix frontend`
- 出力ディレクトリ: `frontend/dist`
- SPA 用のルーティング: すべてのリクエストを `index.html` へフォールバック

> **デプロイ後に Vercel の 404 ページが表示される場合**: Vercel のビルド成果物検出に失敗している可能性があります。その際は、`vercel.json` の `outputDirectory` が `frontend/dist` になっているか確認してください（初期状態では設定済みです）。他の値になっていると、ビルド成果物を見つけられず 404 になります。
>
> **"No FastAPI entrypoint found" と表示される場合**: Vercel の自動検出が Python プロジェクトと誤認しています。新規プロジェクト作成時に以下を必ず設定してください。
>
> - 「Framework preset」を **Other**（もしくは Vite）に変更し、サーバーレス（Python）プリセットを選ばない。
> - 「Root Directory」を `frontend` に変更する。Git 連携後に `Edit` から変更可能です。
> - 変更後に再デプロイすると、`vercel.json` の設定に基づいて静的サイトとしてビルドされます。
> - CLI でデプロイする場合は `vercel --cwd frontend`（本番は `vercel --cwd frontend --prod`）を使用すると、同様にフロントエンドだけが対象になります。

> **重要**: 本プロジェクトのバックエンド（FastAPI + Tesseract OCR）は Vercel 上ではそのまま動作しません。Tesseract や Poppler などのネイティブ依存関係を含むため、Vercel とは別の環境（例: Cloud Run、Render、VPS など）にデプロイし、`VITE_API_URL` をそのバックエンドの公開URLに向けてください。また、Vercel の自動検出で Python プロジェクトと誤認されないよう、リポジトリ直下に `.vercelignore` を配置してバックエンド関連ファイルをアップロード対象から除外しています。

### 手順サマリー

1. バックエンドを任意のサーバーにデプロイし、HTTPS で公開する。
2. Vercel のダッシュボードで新規プロジェクトを作成し、本リポジトリを接続する。
3. 「Root Directory」を `frontend` に変更し、「Framework preset」を **Other** または **Vite** に設定する。
4. 「Environment Variables」に `VITE_API_URL` を追加し、手順1で公開したバックエンドの `/convert` エンドポイントを指定する。
5. 保存後にデプロイを開始すると、`vercel.json` の設定に従って `frontend/dist` が公開される。
6. CLI デプロイの場合は `vercel --cwd frontend --prod` を使用すると同じ構成になります。

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
