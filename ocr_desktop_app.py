"""Tkinterを用いたスタンドアロンのOCRデスクトップアプリ。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from image_pdf_ocr import (
    OCRConversionError,
    create_searchable_pdf,
    extract_text_to_file,
)


class OCRDesktopApp:
    """画像PDFを処理する簡易デスクトップアプリケーション。"""

    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.master.title("Image PDF OCR Suite")
        self.master.geometry("720x520")

        self.input_path = tk.StringVar()
        self.output_pdf_path = tk.StringVar()
        self.output_text_path = tk.StringVar()

        self._create_widgets()

    # UI構築
    def _create_widgets(self) -> None:
        input_frame = tk.LabelFrame(self.master, text="入力PDF")
        input_frame.pack(fill=tk.X, padx=12, pady=(12, 6))

        input_entry = tk.Entry(input_frame, textvariable=self.input_path)
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_input_btn = tk.Button(
            input_frame, text="参照", width=10, command=self._select_input_file
        )
        browse_input_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        output_pdf_frame = tk.LabelFrame(self.master, text="検索可能PDFの出力先")
        output_pdf_frame.pack(fill=tk.X, padx=12, pady=6)

        output_pdf_entry = tk.Entry(
            output_pdf_frame, textvariable=self.output_pdf_path
        )
        output_pdf_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_output_pdf_btn = tk.Button(
            output_pdf_frame,
            text="保存先",
            width=10,
            command=self._select_output_pdf,
        )
        browse_output_pdf_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        output_text_frame = tk.LabelFrame(self.master, text="抽出テキストの保存先")
        output_text_frame.pack(fill=tk.X, padx=12, pady=6)

        output_text_entry = tk.Entry(
            output_text_frame, textvariable=self.output_text_path
        )
        output_text_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_output_text_btn = tk.Button(
            output_text_frame,
            text="保存先",
            width=10,
            command=self._select_output_text,
        )
        browse_output_text_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        button_frame = tk.Frame(self.master)
        button_frame.pack(fill=tk.X, padx=12, pady=(6, 0))

        self.convert_btn = tk.Button(
            button_frame, text="検索可能PDFを作成", command=self._start_conversion
        )
        self.convert_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.extract_btn = tk.Button(
            button_frame, text="テキストを抽出", command=self._start_extraction
        )
        self.extract_btn.pack(side=tk.LEFT, padx=6)

        clear_btn = tk.Button(button_frame, text="ログをクリア", command=self._clear_log)
        clear_btn.pack(side=tk.LEFT, padx=6)

        self.log_widget = ScrolledText(self.master, height=16, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 12))

    # ファイルダイアログ
    def _select_input_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="PDFファイルを選択",
            filetypes=(("PDF", "*.pdf"), ("すべてのファイル", "*.*")),
        )
        if file_path:
            self.input_path.set(file_path)
            self._suggest_output_paths(Path(file_path))

    def _select_output_pdf(self) -> None:
        default = Path(self.output_pdf_path.get()) if self.output_pdf_path.get() else None
        initialdir = default.parent if default else None
        initialfile = default.name if default else None
        file_path = filedialog.asksaveasfilename(
            title="検索可能PDFの保存先",
            defaultextension=".pdf",
            initialdir=initialdir,
            initialfile=initialfile,
            filetypes=(("PDF", "*.pdf"),),
        )
        if file_path:
            self.output_pdf_path.set(file_path)

    def _select_output_text(self) -> None:
        default = (
            Path(self.output_text_path.get()) if self.output_text_path.get() else None
        )
        initialdir = default.parent if default else None
        initialfile = default.name if default else None
        file_path = filedialog.asksaveasfilename(
            title="抽出テキストの保存先",
            defaultextension=".txt",
            initialdir=initialdir,
            initialfile=initialfile,
            filetypes=(("テキスト", "*.txt"), ("すべてのファイル", "*.*")),
        )
        if file_path:
            self.output_text_path.set(file_path)

    # バリデーション
    def _validate_input(self) -> Path | None:
        if not self.input_path.get():
            self._show_error("入力PDFを選択してください。")
            return None
        input_path = Path(self.input_path.get())
        if not input_path.exists():
            self._show_error("指定された入力PDFが見つかりません。")
            return None
        return input_path

    # スレッドユーティリティ
    def _run_in_thread(self, target: Callable[[], None]) -> None:
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.convert_btn.configure(state=state)
        self.extract_btn.configure(state=state)

    def _start_conversion(self) -> None:
        input_path = self._validate_input()
        if not input_path:
            return

        output_path_str = self.output_pdf_path.get().strip()
        if not output_path_str:
            self._show_error("検索可能PDFの保存先を指定してください。")
            return
        output_path = Path(output_path_str)

        self._set_busy(True)
        self._run_in_thread(
            lambda: self._convert_task(input_path=input_path, output_path=output_path)
        )

    def _start_extraction(self) -> None:
        input_path = self._validate_input()
        if not input_path:
            return

        output_path_str = self.output_text_path.get().strip()
        if not output_path_str:
            self._show_error("テキストファイルの保存先を指定してください。")
            return
        output_path = Path(output_path_str)

        self._set_busy(True)
        self._run_in_thread(
            lambda: self._extract_task(input_path=input_path, output_path=output_path)
        )

    # 実際の処理
    def _convert_task(self, input_path: Path, output_path: Path) -> None:
        self._log(f"検索可能PDFを生成中: {output_path}")
        try:
            create_searchable_pdf(input_path, output_path)
        except (FileNotFoundError, OCRConversionError) as exc:
            message = str(exc)
            self._log(f"エラー: {message}")
            self._notify(lambda msg=message: self._show_error(msg))
        except Exception as exc:  # 予期しない例外
            self._log(f"予期しないエラー: {exc}")
            self._notify(lambda: self._show_error("変換に失敗しました。詳細はログを参照してください。"))
        else:
            self._log("検索可能PDFの作成が完了しました。")
            self._notify(
                lambda: messagebox.showinfo(
                    "完了", f"検索可能なPDFを保存しました:\n{output_path}"
                )
            )
        finally:
            self._notify(lambda: self._set_busy(False))

    def _extract_task(self, input_path: Path, output_path: Path) -> None:
        self._log(f"テキストを抽出中: {output_path}")
        try:
            extract_text_to_file(input_path, output_path)
        except (FileNotFoundError, OCRConversionError) as exc:
            message = str(exc)
            self._log(f"エラー: {message}")
            self._notify(lambda msg=message: self._show_error(msg))
        except Exception as exc:
            self._log(f"予期しないエラー: {exc}")
            self._notify(lambda: self._show_error("テキスト抽出に失敗しました。詳細はログを参照してください。"))
        else:
            self._log("テキスト抽出が完了しました。")
            self._notify(
                lambda: messagebox.showinfo(
                    "完了", f"テキストを保存しました:\n{output_path}"
                )
            )
        finally:
            self._notify(lambda: self._set_busy(False))

    # ユーティリティ
    def _suggest_output_paths(self, input_path: Path) -> None:
        stem = input_path.stem
        parent = input_path.parent
        if not self.output_pdf_path.get():
            self.output_pdf_path.set(str(parent / f"{stem}_searchable.pdf"))
        if not self.output_text_path.get():
            self.output_text_path.set(str(parent / f"{stem}_text.txt"))

    def _notify(self, callback: Callable[[], None]) -> None:
        self.master.after(0, callback)

    def _log(self, message: str) -> None:
        def append() -> None:
            self.log_widget.configure(state=tk.NORMAL)
            self.log_widget.insert(tk.END, message + "\n")
            self.log_widget.see(tk.END)
            self.log_widget.configure(state=tk.DISABLED)

        self._notify(append)

    def _show_error(self, message: str) -> None:
        messagebox.showerror("エラー", message)

    def _clear_log(self) -> None:
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state=tk.DISABLED)


def main() -> None:
    root = tk.Tk()
    app = OCRDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
