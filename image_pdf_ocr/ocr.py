"""OCR機能を提供するモジュール。"""

from __future__ import annotations

import io
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Tuple, Union

import fitz  # type: ignore
import pytesseract
import pandas as pd
from PIL import Image, ImageOps
from shutil import which


class OCRConversionError(RuntimeError):
    """OCR変換処理で発生した例外。"""
_AVERAGE_CONFIDENCE_THRESHOLD = float(os.environ.get("OCR_CONFIDENCE_THRESHOLD", "65"))
_TEXT_RENDER_CONFIDENCE_THRESHOLD = 50.0
_UPSCALE_FACTOR = 1.5
_FONT_PATH_CACHE: Path | None = None


@dataclass
class AdaptiveOCRResult:
    """OCR結果と判定情報を保持するデータクラス。"""

    frame: pd.DataFrame
    average_confidence: float
    image_for_string: Image.Image
    used_preprocessing: bool


def _perform_adaptive_ocr(image: Image.Image) -> AdaptiveOCRResult:
    """平均信頼度に応じて前処理を適用し、最適なOCR結果を返す。"""

    base_image = image.convert("RGB")
    base_frame_raw = _image_to_data(base_image)
    base_average = _compute_average_confidence(base_frame_raw)
    base_frame = _prepare_frame(base_frame_raw, scale=1.0)

    best_result = AdaptiveOCRResult(
        frame=base_frame,
        average_confidence=base_average,
        image_for_string=base_image,
        used_preprocessing=False,
    )

    if base_average >= _AVERAGE_CONFIDENCE_THRESHOLD:
        return best_result

    preprocessed_image, scale = _preprocess_for_ocr(base_image)
    processed_frame_raw = _image_to_data(preprocessed_image)
    processed_average = _compute_average_confidence(processed_frame_raw)
    processed_frame = _prepare_frame(processed_frame_raw, scale=scale)

    if processed_average > best_result.average_confidence:
        return AdaptiveOCRResult(
            frame=processed_frame,
            average_confidence=processed_average,
            image_for_string=preprocessed_image,
            used_preprocessing=True,
        )

    return best_result


def _image_to_data(image: Image.Image) -> pd.DataFrame:
    """pytesseractを用いてOCR結果をDataFrameで取得する。"""

    return pytesseract.image_to_data(
        image, lang="jpn", output_type=pytesseract.Output.DATAFRAME
    )


def _compute_average_confidence(frame: pd.DataFrame) -> float:
    """OCR結果の平均信頼度を算出する。"""

    if "conf" not in frame.columns:
        return 0.0

    confidences = pd.to_numeric(frame["conf"], errors="coerce")
    valid = confidences[(confidences.notna()) & (confidences >= 0)]

    if valid.empty:
        return 0.0

    return float(valid.mean())


def _prepare_frame(frame: pd.DataFrame, scale: float) -> pd.DataFrame:
    """数値列をfloat化し、必要に応じて座標をスケールダウンする。"""

    prepared = frame.copy()

    for column in ("left", "top", "width", "height", "conf"):
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    if scale != 1.0:
        for column in ("left", "top", "width", "height"):
            if column in prepared.columns:
                prepared[column] = prepared[column] / scale

    return prepared


def _filter_frame_by_confidence(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """指定した信頼度以上の行だけを残したDataFrameを返す。"""

    if "conf" not in frame.columns:
        return frame.iloc[0:0]

    confidences = pd.to_numeric(frame["conf"], errors="coerce")
    mask = confidences >= threshold
    filtered = frame.loc[mask].copy()
    filtered["text"] = filtered["text"].fillna("") if "text" in filtered.columns else ""
    return filtered


def _preprocess_for_ocr(image: Image.Image) -> Tuple[Image.Image, float]:
    """OCR精度向上のための前処理（拡大＋二値化）を適用する。"""

    grayscale = image.convert("L")
    scale = _UPSCALE_FACTOR
    if scale != 1.0:
        new_size = (int(grayscale.width * scale), int(grayscale.height * scale))
        resized = grayscale.resize(new_size, Image.LANCZOS)
    else:
        resized = grayscale

    enhanced = ImageOps.autocontrast(resized)
    threshold = 180
    binary = enhanced.point(lambda x: 255 if x > threshold else 0, mode="L")
    return binary, scale


def _extract_coordinates(row: pd.Series) -> Tuple[float | None, float | None, float | None]:
    """DataFrameの1行から座標情報を抽出する。"""

    try:
        x = float(row.get("left"))
        y = float(row.get("top"))
        h = float(row.get("height"))
    except (TypeError, ValueError):
        return None, None, None

    if any(math.isnan(value) for value in (x, y, h)):
        return None, None, None

    return x, y, h


def _format_duration(seconds: float) -> str:
    """秒数から可読な時間文字列を生成する。"""

    if not math.isfinite(seconds):
        return "不明"

    total_seconds = max(0, int(round(seconds)))
    minutes, sec = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def _build_progress_message(current: int, total: int, start_time: float) -> str:
    """進捗状況と推定残り時間のメッセージを生成する。"""

    if total <= 0:
        return "進捗: ページ数が不明です"

    elapsed = time.perf_counter() - start_time
    average_per_page = elapsed / current if current else float("inf")
    remaining_pages = max(total - current, 0)
    remaining_estimate = average_per_page * remaining_pages
    remaining_text = _format_duration(remaining_estimate)

    return f"{current}/{total}ページ完了　残り推定時間: {remaining_text}"


def _find_japanese_font_path() -> Path:
    """日本語描画可能なフォントファイルを探索して返す。"""

    global _FONT_PATH_CACHE

    if _FONT_PATH_CACHE and _FONT_PATH_CACHE.exists():
        return _FONT_PATH_CACHE

    env_font = os.environ.get("OCR_JPN_FONT")
    if env_font:
        font_path = Path(env_font).expanduser()
        if font_path.exists():
            _FONT_PATH_CACHE = font_path
            return font_path

    candidate_files = [
        "NotoSansCJK-Regular.ttc",
        "NotoSansCJKjp-Regular.otf",
        "NotoSerifCJK-Regular.ttc",
        "SourceHanSansJP-Regular.otf",
        "SourceHanSerifJP-Regular.otf",
        "ipaexg.ttf",
        "ipaexm.ttf",
        "ipag.ttf",
        "ipam.ttf",
        "YuGothR.ttc",
        "YuMincho.ttc",
    ]

    candidate_patterns = [
        "*NotoSansCJK*.ttc",
        "*NotoSansCJK*.otf",
        "*NotoSerifCJK*.ttc",
        "*NotoSerifCJK*.otf",
        "*SourceHanSans*.otf",
        "*SourceHanSerif*.otf",
        "*ipaex*.ttf",
        "*ipaex*.otf",
        "*ipag*.ttf",
        "*ipag*.ttc",
        "*ipam*.ttf",
        "*ipam*.ttc",
        "*YuGoth*.ttc",
        "*YuMincho*.ttc",
    ]

    directories = _candidate_font_directories()

    for directory in directories:
        for name in candidate_files:
            path = directory / name
            if path.exists():
                _FONT_PATH_CACHE = path
                return path

    for directory in directories:
        if not directory.exists():
            continue
        for pattern in candidate_patterns:
            matches = sorted(directory.rglob(pattern))
            for match in matches:
                if match.is_file():
                    _FONT_PATH_CACHE = match
                    return match

    raise OCRConversionError(
        "日本語フォントが見つかりません。Noto Sans CJKなどのフォントをインストールし、"
        "環境変数 OCR_JPN_FONT でフォントファイルへのパスを指定してください。"
    )


def _candidate_font_directories() -> list[Path]:
    """日本語フォント探索対象となるディレクトリ一覧を返す。"""

    dirs: list[Path] = []

    for env_name in ("OCR_JPN_FONT_DIR", "OCR_FONT_DIR"):
        env_value = os.environ.get(env_name)
        if env_value:
            dirs.append(Path(env_value).expanduser())

    home = Path.home()
    dirs.extend(
        [
            home / ".fonts",
            home / ".local/share/fonts",
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Application Support/Microsoft/Fonts"),
        ]
    )

    module_dir = Path(__file__).resolve().parent
    dirs.append(module_dir)
    dirs.append(module_dir / "fonts")

    if os.name == "nt":
        windir = Path(os.environ.get("WINDIR", "C:/Windows"))
        dirs.append(windir / "Fonts")

    seen: dict[Path, None] = {}
    ordered_dirs: list[Path] = []
    for directory in dirs:
        resolved = directory.resolve()
        if resolved not in seen:
            seen[resolved] = None
            ordered_dirs.append(resolved)

    return ordered_dirs


def _validate_tesseract_setting() -> bool:
    """設定済みの`tesseract_cmd`が妥当かを確認する。"""

    try:
        pytesseract.get_tesseract_version()
        return True
    except pytesseract.TesseractNotFoundError:
        return False


def _try_assign_candidates(paths: Iterable[Path]) -> bool:
    """候補パス群から`tesseract_cmd`を設定し、利用可能か検証する。"""

    for candidate in paths:
        if candidate and candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            if _validate_tesseract_setting():
                return True
    return False


def find_and_set_tesseract_path() -> bool:
    """環境に応じてTesseractの実行ファイルを検出して設定する。"""

    def _set_cmd_if_exists(path: Path) -> bool:
        if path.exists():
            pytesseract.pytesseract.tesseract_cmd = str(path)
            return True
        return False

    # 環境変数で明示的に指定されている場合を優先する
    for env_name in ("TESSERACT_CMD", "TESSERACT_PATH", "PIL_TESSERACT_CMD"):
        env_value = os.environ.get(env_name)
        if env_value and _set_cmd_if_exists(Path(env_value)):
            break

    # すでに設定済みの場合やPATHで検出できた場合はそのまま利用する
    if pytesseract.pytesseract.tesseract_cmd and _validate_tesseract_setting():
        return True

    cmd_from_path = which("tesseract")
    if cmd_from_path and _set_cmd_if_exists(Path(cmd_from_path)):
        if _validate_tesseract_setting():
            return True

    # Windows向けの既定インストールパスをチェック
    path_64 = Path(r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
    path_32 = Path(r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe")

    if _set_cmd_if_exists(path_64) or _set_cmd_if_exists(path_32):
        if _validate_tesseract_setting():
            return True

    # PyInstaller等で配布する際に同梱した`tesseract.exe`を探索
    candidate_roots: list[Path] = []

    if getattr(sys, "frozen", False):  # PyInstaller実行ファイル
        candidate_roots.append(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate_roots.append(Path(meipass))
    module_dir = Path(__file__).resolve().parent
    candidate_roots.append(module_dir)
    candidate_roots.append(module_dir.parent)

    exe_name = "tesseract.exe" if os.name == "nt" else "tesseract"
    bundle_dirs = ("", "Tesseract-OCR", "tesseract", "tesseract-ocr", "bin")

    bundle_candidates = [
        root / sub_dir / exe_name for root in candidate_roots for sub_dir in bundle_dirs
    ]

    if _try_assign_candidates(bundle_candidates):
        return True

    return _validate_tesseract_setting()


def create_searchable_pdf(
    input_path: Union[str, os.PathLike],
    output_path: Union[str, os.PathLike],
    progress_callback: Callable[[str], None] | None = None,
) -> None:
    """画像PDFをOCRして検索可能なPDFを生成する。"""
    if not find_and_set_tesseract_path():
        raise OCRConversionError("Tesseract-OCRが見つかりません。インストールとPATH設定を確認してください。")

    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_path}")

    _prepare_output_path(output_path)

    font_path = _find_japanese_font_path()

    try:
        input_doc = fitz.open(input_path)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - PyMuPDF例外
        raise OCRConversionError(f"PDFファイルを開けませんでした: {exc}") from exc

    output_doc = fitz.open()

    total_pages = input_doc.page_count
    start_time = time.perf_counter()

    def _dispatch_progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)
        else:
            print(message, flush=True)

    if total_pages == 0:
        _dispatch_progress("ページが存在しないPDFです。処理を終了します。")

    try:
        for index, page in enumerate(input_doc, start=1):
            pix = page.get_pixmap(dpi=300)
            image_bytes = io.BytesIO(pix.tobytes("png"))
            with Image.open(image_bytes) as pil_image:
                ocr_result = _perform_adaptive_ocr(pil_image)

            filtered = _filter_frame_by_confidence(
                ocr_result.frame, _TEXT_RENDER_CONFIDENCE_THRESHOLD
            )

            new_page = output_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, pixmap=pix)

            for _, row in filtered.iterrows():
                text = str(row.get("text", "")).strip()
                if not text:
                    continue
                x, y, h = _extract_coordinates(row)
                if x is None or y is None or h is None:
                    continue
                try:
                    new_page.insert_text(
                        (x, y + h),
                        text,
                        fontfile=str(font_path),
                        fontsize=h * 0.8,
                        render_mode=3,
                    )
                except RuntimeError:
                    # PyMuPDFのフォント描画で稀に失敗するケースがあるため無視
                    continue

            message = _build_progress_message(index, total_pages, start_time)
            _dispatch_progress(message)
    except Exception as exc:
        raise OCRConversionError(f"ページ処理中に問題が発生しました: {exc}") from exc
    finally:
        input_doc.close()

    try:
        output_doc.save(output_path, garbage=4, deflate=True, clean=True)
    except PermissionError as exc:
        raise OCRConversionError(
            f"PDFを書き込めませんでした。権限を確認してください: {exc}"
        ) from exc
    except Exception as exc:  # pragma: no cover - save時のPyMuPDF例外
        raise OCRConversionError(f"PDFを保存できませんでした: {exc}") from exc
    finally:
        output_doc.close()


def extract_text_from_image_pdf(
    input_path: Union[str, os.PathLike],
    progress_callback: Callable[[str], None] | None = None,
) -> str:
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
    total_pages = document.page_count
    start_time = time.perf_counter()

    def _dispatch_progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)
        else:
            print(message, flush=True)

    if total_pages == 0:
        _dispatch_progress("ページが存在しないPDFです。処理を終了します。")
        document.close()
        return "\n"
    try:
        for index, page in enumerate(document, start=1):
            pix = page.get_pixmap(dpi=300)
            image_bytes = io.BytesIO(pix.tobytes("png"))
            with Image.open(image_bytes) as pil_image:
                ocr_result = _perform_adaptive_ocr(pil_image)
                page_text = pytesseract.image_to_string(ocr_result.image_for_string, lang="jpn")
            texts.append(f"--- ページ {index} ---\n{page_text.strip()}\n")

            message = _build_progress_message(index, total_pages, start_time)
            _dispatch_progress(message)
    except Exception as exc:
        raise OCRConversionError(f"テキスト抽出中に問題が発生しました: {exc}") from exc
    finally:
        document.close()

    return "\n".join(texts).strip() + "\n"


def extract_text_to_file(
    input_path: Union[str, os.PathLike],
    output_path: Union[str, os.PathLike],
    progress_callback: Callable[[str], None] | None = None,
) -> None:
    """画像PDFから抽出したテキストをファイルに保存する。"""

    text = extract_text_from_image_pdf(
        input_path, progress_callback=progress_callback
    )
    output_path = Path(output_path)
    _prepare_output_path(output_path)

    try:
        output_path.write_text(text, encoding="utf-8")
    except PermissionError as exc:
        raise OCRConversionError(
            f"テキストを書き込めませんでした。権限を確認してください: {exc}"
        ) from exc
    except OSError as exc:
        raise OCRConversionError(f"テキストファイルを保存できませんでした: {exc}") from exc


def _prepare_output_path(path: Path) -> None:
    """出力パスの親ディレクトリを作成し、書き込み可能か確認する。"""

    try:
        parent = path.parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # pragma: no cover - filesystem permissions vary
        raise OCRConversionError(
            f"出力先ディレクトリを作成できませんでした: {exc}"
        ) from exc

    if path.exists() and path.is_dir():
        raise OCRConversionError(f"出力パスがディレクトリを指しています: {path}")

