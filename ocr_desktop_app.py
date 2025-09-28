"""Tkinterを用いたスタンドアロンのOCRデスクトップアプリ。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from image_pdf_ocr import (
    OCRCancelledError,
    OCRConversionError,
    PDFPasswordRemovalError,
    create_searchable_pdf,
    create_searchable_pdf_from_images,
    extract_text_to_file,
    remove_pdf_password,
)
from PIL import Image, ImageTk


class ProcessingWorkspace:
    """単一のOCR処理画面を構築・管理する。"""

    def __init__(self, app: "OCRDesktopApp", parent: tk.Widget) -> None:
        self.root = app.master
        self.frame = tk.Frame(parent)

        self.input_path = tk.StringVar()
        self.output_pdf_path = tk.StringVar()
        self.output_text_path = tk.StringVar()
        self.status_var = tk.StringVar(value="準備完了")

        self.mode_var = tk.StringVar(value="searchable_pdf")
        self.mode_hint_var = tk.StringVar(value="")
        self.mode_buttons: list[ttk.Radiobutton] = []
        self.mode_hint_label: tk.Label | None = None
        self.start_btn: tk.Button | None = None
        self.cancel_btn: tk.Button | None = None
        self.clear_btn: tk.Button | None = None
        self.clear_log_btn: tk.Button | None = None
        self.log_widget: ScrolledText | None = None
        self.progress: ttk.Progressbar | None = None
        self.output_pdf_entry: tk.Entry | None = None
        self.output_text_entry: tk.Entry | None = None
        self.browse_output_pdf_btn: tk.Button | None = None
        self.browse_output_text_btn: tk.Button | None = None
        self.output_pdf_frame: tk.LabelFrame | None = None
        self.output_text_frame: tk.LabelFrame | None = None

        self._worker: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._last_auto_pdf_path: Path | None = None
        self._last_auto_text_path: Path | None = None

        self._create_widgets()

    # --- ライフサイクル -------------------------------------------------
    def pack(self, *, side: str, padx: tuple[int, int], pady: tuple[int, int]) -> None:
        self.frame.pack(side=side, fill=tk.BOTH, expand=True, padx=padx, pady=pady)

    def grid(
        self,
        *,
        row: int,
        column: int,
        padx: tuple[int, int],
        pady: tuple[int, int],
        sticky: str,
    ) -> None:
        self.frame.grid(row=row, column=column, padx=padx, pady=pady, sticky=sticky)

    def prepare_for_destroy(self) -> None:
        self._cancel_running_task()
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=0.1)

    def destroy(self) -> None:
        self.frame.destroy()

    # --- UI構築 ---------------------------------------------------------
    def _create_widgets(self) -> None:
        container = tk.Frame(self.frame)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        left_frame = tk.Frame(container)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right_frame = tk.Frame(container)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        input_frame = tk.LabelFrame(left_frame, text="入力PDF")
        input_frame.pack(fill=tk.X, pady=(0, 8))

        input_entry = tk.Entry(input_frame, textvariable=self.input_path)
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_input_btn = tk.Button(
            input_frame, text="参照", width=10, command=self._select_input_file
        )
        browse_input_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        self.output_pdf_frame = tk.LabelFrame(left_frame, text="検索可能PDFの保存先")
        self.output_pdf_frame.pack(fill=tk.X, pady=(0, 8))

        self.output_pdf_entry = tk.Entry(
            self.output_pdf_frame, textvariable=self.output_pdf_path
        )
        self.output_pdf_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        self.browse_output_pdf_btn = tk.Button(
            self.output_pdf_frame,
            text="保存先",
            width=10,
            command=self._select_output_pdf,
        )
        self.browse_output_pdf_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        self.output_text_frame = tk.LabelFrame(left_frame, text="抽出テキストの保存先")
        self.output_text_frame.pack(fill=tk.X, pady=(0, 8))

        self.output_text_entry = tk.Entry(
            self.output_text_frame, textvariable=self.output_text_path
        )
        self.output_text_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        self.browse_output_text_btn = tk.Button(
            self.output_text_frame,
            text="保存先",
            width=10,
            command=self._select_output_text,
        )
        self.browse_output_text_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        mode_frame = tk.LabelFrame(left_frame, text="処理内容")
        mode_frame.pack(fill=tk.X, pady=(0, 8))

        pdf_radio = ttk.Radiobutton(
            mode_frame,
            text="検索可能PDFを作成",
            value="searchable_pdf",
            variable=self.mode_var,
            command=self._on_mode_changed,
        )
        pdf_radio.pack(anchor=tk.W, padx=12, pady=(8, 2))
        self.mode_buttons.append(pdf_radio)

        text_radio = ttk.Radiobutton(
            mode_frame,
            text="テキストを抽出",
            value="extract_text",
            variable=self.mode_var,
            command=self._on_mode_changed,
        )
        text_radio.pack(anchor=tk.W, padx=12, pady=(0, 8))
        self.mode_buttons.append(text_radio)

        self.mode_hint_var.set(
            "検索可能なPDFを作成します。保存先を確認してから実行してください。"
        )
        self.mode_hint_label = tk.Label(
            left_frame,
            textvariable=self.mode_hint_var,
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=320,
            fg="#555555",
        )
        self.mode_hint_label.pack(fill=tk.X, padx=4, pady=(0, 8))

        button_frame = tk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=(0, 8))

        self.start_btn = tk.Button(
            button_frame,
            text="処理を開始",
            command=self._start_processing,
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6), ipadx=6, ipady=2)

        self.cancel_btn = tk.Button(
            button_frame,
            text="キャンセル",
            state=tk.DISABLED,
            command=self._cancel_running_task,
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=6)

        self.clear_btn = tk.Button(
            button_frame,
            text="リセット",
            command=self._clear_workspace,
            relief=tk.FLAT,
            cursor="hand2",
            fg="#444444",
        )
        self.clear_btn.pack(side=tk.RIGHT)

        status_frame = tk.LabelFrame(left_frame, text="進行状況")
        status_frame.pack(fill=tk.X)

        self.progress = ttk.Progressbar(status_frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=12, pady=(12, 4))

        status_label = tk.Label(status_frame, textvariable=self.status_var, anchor=tk.W)
        status_label.pack(fill=tk.X, padx=12, pady=(0, 12))

        log_frame = tk.LabelFrame(right_frame, text="処理ログ")
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_toolbar = tk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, padx=12, pady=(12, 0))

        self.clear_log_btn = tk.Button(log_toolbar, text="ログをクリア", command=self._clear_log)
        self.clear_log_btn.pack(side=tk.RIGHT)
        self.clear_log_btn.configure(state=tk.DISABLED)

        self.log_widget = ScrolledText(log_frame, height=18, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 12))

        self._update_mode_dependent_widgets()

    # --- ファイルダイアログ ---------------------------------------------
    def _select_input_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="PDFファイルを選択",
            filetypes=(("PDF", "*.pdf"), ("すべてのファイル", "*.*")),
        )
        if file_path:
            self.input_path.set(file_path)
            self._suggest_output_paths(Path(file_path))

    def _select_output_pdf(self) -> None:
        current = self.output_pdf_path.get()
        default = Path(current) if current else None
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
            self._last_auto_pdf_path = None

    def _select_output_text(self) -> None:
        current = self.output_text_path.get()
        default = Path(current) if current else None
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
            self._last_auto_text_path = None

    # --- バリデーション -------------------------------------------------
    def _validate_input(self) -> Path | None:
        if not self.input_path.get():
            self._show_error("入力PDFを選択してください。")
            return None
        input_path = Path(self.input_path.get())
        if not input_path.exists():
            self._show_error("指定された入力PDFが見つかりません。")
            return None
        return input_path

    # --- スレッド制御 ---------------------------------------------------
    def _run_in_thread(self, target: Callable[[], None]) -> None:
        def wrapper() -> None:
            try:
                target()
            finally:
                self._worker = None
                self._cancel_event = None
                self._notify(lambda: self._set_busy(False))

        self._worker = threading.Thread(target=wrapper, daemon=True)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL

        if self.start_btn:
            if busy:
                self.start_btn.configure(state=tk.DISABLED, text="処理中…")
            else:
                self.start_btn.configure(state=tk.NORMAL)
        for radio in self.mode_buttons:
            radio.configure(state=state)
        if self.cancel_btn:
            self.cancel_btn.configure(state=tk.NORMAL if busy else tk.DISABLED)
        if self.clear_btn:
            self.clear_btn.configure(state=state)
        if self.clear_log_btn:
            if busy:
                self.clear_log_btn.configure(state=tk.DISABLED)
            else:
                has_log = bool(
                    self.log_widget
                    and self.log_widget.get("1.0", tk.END).strip()
                )
                self.clear_log_btn.configure(
                    state=tk.NORMAL if has_log else tk.DISABLED
                )
        if self.progress:
            if busy:
                self.progress.start(10)
            else:
                self.progress.stop()

        if not busy:
            self._update_mode_dependent_widgets()

    def _cancel_running_task(self) -> None:
        if self._cancel_event and not self._cancel_event.is_set():
            self._cancel_event.set()
            self._log("キャンセル要求を送信しました。")
            self._notify(lambda: self._update_status("キャンセルしています…"))

    def _on_mode_changed(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._update_mode_dependent_widgets()

    def _start_processing(self) -> None:
        if self.mode_var.get() == "extract_text":
            self._start_extraction()
        else:
            self._start_conversion()

    # --- ボタン操作 -----------------------------------------------------
    def _start_conversion(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        input_path = self._validate_input()
        if not input_path:
            return

        output_path_str = self.output_pdf_path.get().strip()
        if not output_path_str:
            self._show_error("検索可能PDFの保存先を指定してください。")
            return
        output_path = Path(output_path_str)

        if output_path.suffix.lower() != ".pdf":
            self._show_error("保存先には.pdf拡張子を指定してください。")
            return

        if input_path.resolve() == output_path.resolve():
            self._show_error("入力ファイルと同じパスには保存できません。保存先を変更してください。")
            return

        self._cancel_event = threading.Event()
        self._set_busy(True)
        self._update_status("検索可能PDFを生成しています…")
        self._run_in_thread(
            lambda: self._convert_task(input_path=input_path, output_path=output_path)
        )

    def _start_extraction(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        input_path = self._validate_input()
        if not input_path:
            return

        output_path_str = self.output_text_path.get().strip()
        if not output_path_str:
            self._show_error("テキストファイルの保存先を指定してください。")
            return
        output_path = Path(output_path_str)

        if output_path.suffix.lower() not in (".txt", ".md"):
            self._show_error("テキストファイルの保存先には.txtまたは.mdを指定してください。")
            return

        if input_path.resolve() == output_path.resolve():
            self._show_error("入力PDFと同じファイル名には保存できません。")
            return

        self._cancel_event = threading.Event()
        self._set_busy(True)
        self._update_status("テキストを抽出しています…")
        self._run_in_thread(
            lambda: self._extract_task(input_path=input_path, output_path=output_path)
        )

    # --- 実処理 ---------------------------------------------------------
    def _convert_task(self, input_path: Path, output_path: Path) -> None:
        self._log(f"検索可能PDFを生成中: {output_path}")
        try:
            create_searchable_pdf(
                input_path,
                output_path,
                progress_callback=self._make_progress_callback(),
                cancel_event=self._cancel_event,
            )
        except OCRCancelledError:
            self._log("検索可能PDFの作成をキャンセルしました。")
            self._notify(lambda: self._update_status("検索可能PDFの作成をキャンセルしました。"))
        except (FileNotFoundError, OCRConversionError) as exc:
            message = str(exc)
            self._log(f"エラー: {message}")
            self._notify(
                lambda msg=message: (
                    self._show_error(msg),
                    self._update_status("エラーが発生しました。ログをご確認ください。"),
                )
            )
        except Exception as exc:
            self._log(f"予期しないエラー: {exc}")
            self._notify(
                lambda: (
                    self._show_error("変換に失敗しました。詳細はログを参照してください。"),
                    self._update_status("予期しないエラーが発生しました。"),
                )
            )
        else:
            self._log("検索可能PDFの作成が完了しました。")
            self._notify(
                lambda: messagebox.showinfo(
                    "完了", f"検索可能なPDFを保存しました:\n{output_path}"
                )
            )
            self._notify(
                lambda: self._update_status("検索可能PDFの作成が完了しました。")
            )

    def _extract_task(self, input_path: Path, output_path: Path) -> None:
        self._log(f"テキストを抽出中: {output_path}")
        try:
            extract_text_to_file(
                input_path,
                output_path,
                progress_callback=self._make_progress_callback(),
                cancel_event=self._cancel_event,
            )
        except OCRCancelledError:
            self._log("テキスト抽出をキャンセルしました。")
            self._notify(lambda: self._update_status("テキスト抽出をキャンセルしました。"))
        except (FileNotFoundError, OCRConversionError) as exc:
            message = str(exc)
            self._log(f"エラー: {message}")
            self._notify(
                lambda msg=message: (
                    self._show_error(msg),
                    self._update_status("エラーが発生しました。ログをご確認ください。"),
                )
            )
        except Exception as exc:
            self._log(f"予期しないエラー: {exc}")
            self._notify(
                lambda: (
                    self._show_error("テキスト抽出に失敗しました。詳細はログを参照してください。"),
                    self._update_status("予期しないエラーが発生しました。"),
                )
            )
        else:
            self._log("テキスト抽出が完了しました。")
            self._notify(
                lambda: messagebox.showinfo(
                    "完了", f"テキストを保存しました:\n{output_path}"
                )
            )
            self._notify(
                lambda: self._update_status("テキスト抽出が完了しました。")
            )

    # --- UI補助 ---------------------------------------------------------
    def _update_mode_dependent_widgets(self) -> None:
        mode = self.mode_var.get()
        is_pdf_mode = mode != "extract_text"
        pdf_label = "検索可能PDFの保存先"
        text_label = "抽出テキストの保存先"

        if is_pdf_mode:
            hint = (
                "検索可能なPDFを作成します。"
                "保存先を確認して「検索可能PDFを作成」をクリックしてください。"
            )
        else:
            hint = (
                "PDFからテキストを抽出します。"
                "テキストの保存先を確認して「テキストを抽出」をクリックしてください。"
            )
        self.mode_hint_var.set(hint)

        if self.output_pdf_frame:
            suffix = "（必須）" if is_pdf_mode else "（不要）"
            self.output_pdf_frame.configure(text=f"{pdf_label}{suffix}")
        if self.output_text_frame:
            suffix = "（必須）" if not is_pdf_mode else "（不要）"
            self.output_text_frame.configure(text=f"{text_label}{suffix}")

        if self.output_pdf_entry and self.browse_output_pdf_btn:
            pdf_state = tk.NORMAL if is_pdf_mode else tk.DISABLED
            self.output_pdf_entry.configure(state=pdf_state)
            self.browse_output_pdf_btn.configure(state=pdf_state)

        if self.output_text_entry and self.browse_output_text_btn:
            text_state = tk.NORMAL if not is_pdf_mode else tk.DISABLED
            self.output_text_entry.configure(state=text_state)
            self.browse_output_text_btn.configure(state=text_state)

        if self.start_btn and (not self._worker or not self._worker.is_alive()):
            button_text = "検索可能PDFを作成" if is_pdf_mode else "テキストを抽出"
            self.start_btn.configure(text=button_text)

    # --- ユーティリティ -------------------------------------------------
    def _suggest_output_paths(self, input_path: Path) -> None:
        stem = input_path.stem
        parent = input_path.parent
        suggested_pdf = parent / f"{stem}_searchable.pdf"
        current_pdf = self.output_pdf_path.get()
        if not current_pdf or current_pdf == str(self._last_auto_pdf_path):
            self.output_pdf_path.set(str(suggested_pdf))
            self._last_auto_pdf_path = suggested_pdf
        else:
            self._last_auto_pdf_path = None

        suggested_text = parent / f"{stem}_text.txt"
        current_text = self.output_text_path.get()
        if not current_text or current_text == str(self._last_auto_text_path):
            self.output_text_path.set(str(suggested_text))
            self._last_auto_text_path = suggested_text
        else:
            self._last_auto_text_path = None

    def _notify(self, callback: Callable[[], None]) -> None:
        def safe_callback() -> None:
            if self.frame.winfo_exists():
                callback()

        self.root.after(0, safe_callback)

    def _make_progress_callback(self) -> Callable[[str], None]:
        def _callback(message: str) -> None:
            self._log(message)
            self._notify(lambda: self._update_status(message))

        return _callback

    def _update_status(self, message: str) -> None:
        self.status_var.set(message)

    def _log(self, message: str) -> None:
        def append() -> None:
            if not self.log_widget:
                return
            self.log_widget.configure(state=tk.NORMAL)
            self.log_widget.insert(tk.END, message + "\n")
            self.log_widget.see(tk.END)
            self.log_widget.configure(state=tk.DISABLED)
            if self.clear_log_btn:
                self.clear_log_btn.configure(state=tk.NORMAL)

        self._notify(append)

    def _show_error(self, message: str) -> None:
        messagebox.showerror("エラー", message)

    def _clear_log(self) -> None:
        if not self.log_widget:
            return
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state=tk.DISABLED)
        if self.clear_log_btn:
            self.clear_log_btn.configure(state=tk.DISABLED)

    def _clear_workspace(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self.input_path.set("")
        self.output_pdf_path.set("")
        self.output_text_path.set("")
        self.status_var.set("準備完了")
        self._last_auto_pdf_path = None
        self._last_auto_text_path = None
        self._clear_log()
        self._update_mode_dependent_widgets()


class PDFPasswordRemovalWorkspace:
    """PDFのパスワード解除画面を構築・管理する。"""

    def __init__(self, app: "OCRDesktopApp", parent: tk.Widget) -> None:
        self.root = app.master
        self.frame = tk.Frame(parent)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.password = tk.StringVar()
        self.status_var = tk.StringVar(value="準備完了")

        self.remove_btn: tk.Button | None = None
        self.clear_btn: tk.Button | None = None
        self.clear_log_btn: tk.Button | None = None
        self.progress: ttk.Progressbar | None = None
        self.log_widget: ScrolledText | None = None

        self._worker: threading.Thread | None = None

        self._create_widgets()

    def pack(self, *, fill: str, expand: bool, padx: tuple[int, int], pady: tuple[int, int]) -> None:
        self.frame.pack(fill=fill, expand=expand, padx=padx, pady=pady)

    def _create_widgets(self) -> None:
        container = tk.Frame(self.frame)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        left_frame = tk.Frame(container)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right_frame = tk.Frame(container)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        input_frame = tk.LabelFrame(left_frame, text="入力PDF")
        input_frame.pack(fill=tk.X, pady=(0, 8))

        input_entry = tk.Entry(input_frame, textvariable=self.input_path)
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_input_btn = tk.Button(
            input_frame, text="参照", width=10, command=self._select_input_file
        )
        browse_input_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        password_frame = tk.LabelFrame(left_frame, text="PDFパスワード")
        password_frame.pack(fill=tk.X, pady=(0, 8))

        password_label = tk.Label(password_frame, text="パスワードを入力してください。")
        password_label.pack(anchor=tk.W, padx=12, pady=(8, 0))

        password_entry = tk.Entry(password_frame, textvariable=self.password, show="*")
        password_entry.pack(fill=tk.X, padx=12, pady=(4, 12))

        output_frame = tk.LabelFrame(left_frame, text="パスワード解除後の保存先")
        output_frame.pack(fill=tk.X, pady=(0, 8))

        output_entry = tk.Entry(output_frame, textvariable=self.output_path)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_output_btn = tk.Button(
            output_frame, text="保存先", width=10, command=self._select_output_file
        )
        browse_output_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        button_frame = tk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=(0, 8))

        self.remove_btn = tk.Button(
            button_frame, text="パスワードを解除", command=self._start_removal
        )
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.clear_btn = tk.Button(
            button_frame, text="画面をクリア", command=self._clear_workspace
        )
        self.clear_btn.pack(side=tk.LEFT, padx=6)

        status_frame = tk.LabelFrame(left_frame, text="進行状況")
        status_frame.pack(fill=tk.X)

        self.progress = ttk.Progressbar(status_frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=12, pady=(12, 4))

        status_label = tk.Label(status_frame, textvariable=self.status_var, anchor=tk.W)
        status_label.pack(fill=tk.X, padx=12, pady=(0, 12))

        log_frame = tk.LabelFrame(right_frame, text="処理ログ")
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_toolbar = tk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, padx=12, pady=(12, 0))

        self.clear_log_btn = tk.Button(log_toolbar, text="ログをクリア", command=self._clear_log)
        self.clear_log_btn.pack(side=tk.RIGHT)
        self.clear_log_btn.configure(state=tk.DISABLED)

        self.log_widget = ScrolledText(log_frame, height=14, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 12))

    def _select_input_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="パスワード付きPDFを選択",
            filetypes=(("PDF", "*.pdf"), ("すべてのファイル", "*.*")),
        )
        if file_path:
            self.input_path.set(file_path)
            self._suggest_output_path(Path(file_path))

    def _select_output_file(self) -> None:
        current = self.output_path.get()
        default = Path(current) if current else None
        initialdir = default.parent if default else None
        initialfile = default.name if default else None
        file_path = filedialog.asksaveasfilename(
            title="パスワード解除後のPDFの保存先",
            defaultextension=".pdf",
            initialdir=initialdir,
            initialfile=initialfile,
            filetypes=(("PDF", "*.pdf"),),
        )
        if file_path:
            self.output_path.set(file_path)

    def _append_log(self, message: str) -> None:
        if not self.log_widget:
            return
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, message + "\n")
        self.log_widget.see(tk.END)
        self.log_widget.configure(state=tk.DISABLED)
        if self.clear_log_btn:
            self.clear_log_btn.configure(state=tk.NORMAL)

    def _log(self, message: str) -> None:
        self._notify(lambda msg=message: self._append_log(msg))

    def _clear_log(self) -> None:
        if not self.log_widget:
            return
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state=tk.DISABLED)
        if self.clear_log_btn:
            self.clear_log_btn.configure(state=tk.DISABLED)

    def _start_removal(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        input_value = self.input_path.get().strip()
        if not input_value:
            self._append_log("エラー: 入力PDFが未選択です。")
            self._show_error("入力PDFを選択してください。")
            return
        input_path = Path(input_value)
        if not input_path.exists():
            self._append_log("エラー: 指定された入力PDFが見つかりません。")
            self._show_error("指定された入力PDFが見つかりません。")
            return

        output_value = self.output_path.get().strip()
        if not output_value:
            self._append_log("エラー: 保存先が指定されていません。")
            self._show_error("保存先を指定してください。")
            return
        output_path = Path(output_value)
        if output_path.suffix.lower() != ".pdf":
            self._append_log("エラー: 保存先は.pdf拡張子である必要があります。")
            self._show_error("保存先には.pdf拡張子を指定してください。")
            return

        password = self.password.get()
        if not password:
            self._append_log("エラー: パスワードが入力されていません。")
            self._show_error("パスワードを入力してください。")
            return

        self._set_busy(True)
        self._update_status("パスワードを解除しています…")
        self._append_log(
            f"処理開始: {input_path} → {output_path}"
        )
        self._run_in_thread(
            lambda: self._remove_task(
                input_path=input_path, output_path=output_path, password=password
            )
        )

    def _run_in_thread(self, target: Callable[[], None]) -> None:
        def wrapper() -> None:
            try:
                target()
            finally:
                self._worker = None
                self._notify(lambda: self._set_busy(False))

        self._worker = threading.Thread(target=wrapper, daemon=True)
        self._worker.start()

    def _remove_task(self, input_path: Path, output_path: Path, password: str) -> None:
        try:
            remove_pdf_password(input_path, output_path, password)
        except (FileNotFoundError, ValueError, PDFPasswordRemovalError) as exc:
            message = str(exc)
            self._notify(lambda msg=message: self._handle_failure(msg))
        except Exception as exc:  # noqa: BLE001
            message = f"予期しないエラーが発生しました: {exc}"
            self._notify(lambda msg=message: self._handle_failure(msg))
        else:
            def on_success() -> None:
                self._append_log(f"完了: {output_path}")
                messagebox.showinfo(
                    "完了", f"パスワードを解除したPDFを保存しました:\n{output_path}"
                )
                self._update_status("パスワードの解除が完了しました。")

            self._notify(on_success)

    def _handle_failure(self, message: str) -> None:
        self._append_log(f"エラー: {message}")
        self._show_error(message)
        self._update_status("エラーが発生しました。内容を確認してください。")

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        if self.remove_btn:
            self.remove_btn.configure(state=state)
        if self.clear_btn:
            self.clear_btn.configure(state=state)
        if self.progress:
            if busy:
                self.progress.start(10)
            else:
                self.progress.stop()

    def _update_status(self, message: str) -> None:
        self.status_var.set(message)

    def _notify(self, callback: Callable[[], None]) -> None:
        def safe_callback() -> None:
            if self.frame.winfo_exists():
                callback()

        self.root.after(0, safe_callback)

    def _show_error(self, message: str) -> None:
        messagebox.showerror("エラー", message)

    def _suggest_output_path(self, input_path: Path) -> None:
        if not self.output_path.get():
            self.output_path.set(str(input_path.with_name(f"{input_path.stem}_unlocked.pdf")))

    def _clear_workspace(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self.input_path.set("")
        self.output_path.set("")
        self.password.set("")
        self.status_var.set("準備完了")
        self._clear_log()



class ImagesToPDFWorkspace:
    """画像から検索可能PDFを生成するための作業画面。"""

    _preview_max_size = (480, 640)

    def __init__(self, app: "OCRDesktopApp", parent: tk.Widget) -> None:
        self.root = app.master
        self.frame = tk.Frame(parent)

        self.image_paths: list[Path] = []
        self.output_path = tk.StringVar()
        self.status_var = tk.StringVar(value="準備完了")
        self.progress_label_var = tk.StringVar(value="進捗: 0/0ページ")
        self.preview_info_var = tk.StringVar(value="プレビューはまだありません")

        self.step_vars: dict[str, tk.BooleanVar] = {
            "select": tk.BooleanVar(value=False),
            "layout": tk.BooleanVar(value=False),
            "ocr": tk.BooleanVar(value=False),
            "save": tk.BooleanVar(value=False),
        }

        self.image_listbox: tk.Listbox | None = None
        self.log_widget: ScrolledText | None = None
        self.progress_bar: ttk.Progressbar | None = None
        self.preview_label: tk.Label | None = None

        self.add_btn: tk.Button | None = None
        self.remove_btn: tk.Button | None = None
        self.up_btn: tk.Button | None = None
        self.down_btn: tk.Button | None = None
        self.clear_list_btn: tk.Button | None = None
        self.convert_btn: tk.Button | None = None
        self.cancel_btn: tk.Button | None = None
        self.clear_btn: tk.Button | None = None
        self.browse_btn: tk.Button | None = None

        self._worker: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._last_auto_output: Path | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_started = False
        self._ocr_started = False
        self._suspend_output_trace = False

        self.output_path.trace_add('write', lambda *_args: self._on_output_path_changed())

        self._create_widgets()

    # --- ライフサイクル -------------------------------------------------
    def pack(self, *, fill: str, expand: bool, padx: tuple[int, int], pady: tuple[int, int]) -> None:
        self.frame.pack(fill=fill, expand=expand, padx=padx, pady=pady)

    def prepare_for_destroy(self) -> None:
        self._cancel_running_task()
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=0.1)

    def destroy(self) -> None:
        self.frame.destroy()

    # --- UI構築 ---------------------------------------------------------
    def _create_widgets(self) -> None:
        container = tk.Frame(self.frame)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        left_frame = tk.Frame(container)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        preview_frame = tk.LabelFrame(container, text="プレビュー")
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        image_frame = tk.LabelFrame(left_frame, text="入力画像")
        image_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.image_listbox = tk.Listbox(image_frame, selectmode=tk.EXTENDED, height=12)
        self.image_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0), pady=8)
        scrollbar = tk.Scrollbar(image_frame, orient=tk.VERTICAL, command=self.image_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 12), pady=8)
        self.image_listbox.configure(yscrollcommand=scrollbar.set)

        list_btn_frame = tk.Frame(image_frame)
        list_btn_frame.pack(fill=tk.X, padx=12, pady=(0, 8))

        self.add_btn = tk.Button(list_btn_frame, text="画像を追加", command=self._add_images)
        self.add_btn.pack(side=tk.LEFT, padx=2)
        self.remove_btn = tk.Button(list_btn_frame, text="選択を削除", command=self._remove_selected)
        self.remove_btn.pack(side=tk.LEFT, padx=2)
        self.up_btn = tk.Button(list_btn_frame, text="上へ", command=self._move_up)
        self.up_btn.pack(side=tk.LEFT, padx=2)
        self.down_btn = tk.Button(list_btn_frame, text="下へ", command=self._move_down)
        self.down_btn.pack(side=tk.LEFT, padx=2)
        self.clear_list_btn = tk.Button(list_btn_frame, text="一覧をクリア", command=self._clear_images)
        self.clear_list_btn.pack(side=tk.LEFT, padx=2)

        output_frame = tk.LabelFrame(left_frame, text="検索可能PDFの保存先")
        output_frame.pack(fill=tk.X, pady=(0, 8))

        output_entry = tk.Entry(output_frame, textvariable=self.output_path)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        self.browse_btn = tk.Button(output_frame, text="保存先", width=10, command=self._select_output_path)
        self.browse_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        steps_frame = tk.LabelFrame(left_frame, text="進行チェック")
        steps_frame.pack(fill=tk.X, pady=(0, 8))

        step_labels = (
            ("画像の読み込み", self.step_vars["select"]),
            ("ページ整形", self.step_vars["layout"]),
            ("OCR処理", self.step_vars["ocr"]),
            ("PDF保存", self.step_vars["save"]),
        )
        for index, (label, var) in enumerate(step_labels):
            chk = tk.Checkbutton(steps_frame, text=label, variable=var, state=tk.DISABLED)
            chk.grid(row=index // 2, column=index % 2, padx=12, pady=4, sticky='w')

        button_frame = tk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=(0, 8))

        self.convert_btn = tk.Button(button_frame, text="検索可能PDFを生成", command=self._start_conversion)
        self.convert_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.cancel_btn = tk.Button(button_frame, text="キャンセル", state=tk.DISABLED, command=self._cancel_running_task)
        self.cancel_btn.pack(side=tk.LEFT, padx=6)

        self.clear_btn = tk.Button(button_frame, text="画面をクリア", command=self._clear_workspace)
        self.clear_btn.pack(side=tk.LEFT, padx=6)

        progress_frame = tk.Frame(left_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 8))

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X, padx=12, pady=(4, 2))
        self.progress_bar.configure(maximum=1, value=0)

        status_label = tk.Label(progress_frame, textvariable=self.status_var, anchor=tk.W)
        status_label.pack(fill=tk.X, padx=12, pady=(0, 2))

        progress_label = tk.Label(progress_frame, textvariable=self.progress_label_var, anchor=tk.W)
        progress_label.pack(fill=tk.X, padx=12, pady=(0, 4))

        log_frame = tk.LabelFrame(left_frame, text="ログ")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_widget = ScrolledText(log_frame, height=12, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        self.preview_label = tk.Label(
            preview_frame,
            text="プレビューはここに表示されます",
            anchor=tk.CENTER,
            justify=tk.CENTER,
            relief=tk.SUNKEN,
        )
        self.preview_label.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 6))

        preview_info_label = tk.Label(preview_frame, textvariable=self.preview_info_var, anchor=tk.W)
        preview_info_label.pack(fill=tk.X, padx=12, pady=(0, 12))

    # --- ファイル操作 ---------------------------------------------------
    def _add_images(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="画像ファイルを選択",
            filetypes=(("画像ファイル", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"), ("すべてのファイル", "*.*")),
        )
        if not file_paths:
            return

        for path_str in file_paths:
            path = Path(path_str)
            if path not in self.image_paths:
                self.image_paths.append(path)

        self._update_image_listbox()
        self._suggest_output_path()
        self._update_step_flags()

    def _remove_selected(self) -> None:
        if not self.image_listbox:
            return
        selection = list(self.image_listbox.curselection())
        if not selection:
            return
        for index in sorted(selection, reverse=True):
            if 0 <= index < len(self.image_paths):
                del self.image_paths[index]
        self._update_image_listbox()
        self._update_step_flags()

    def _move_up(self) -> None:
        if not self.image_listbox:
            return
        selection = sorted(self.image_listbox.curselection())
        if not selection:
            return
        for index in selection:
            if index <= 0:
                continue
            self.image_paths[index - 1], self.image_paths[index] = (
                self.image_paths[index],
                self.image_paths[index - 1],
            )
        self._update_image_listbox()
        self.image_listbox.selection_clear(0, tk.END)
        for index in selection:
            self.image_listbox.selection_set(max(index - 1, 0))

    def _move_down(self) -> None:
        if not self.image_listbox:
            return
        selection = sorted(self.image_listbox.curselection(), reverse=True)
        if not selection:
            return
        for index in selection:
            if index >= len(self.image_paths) - 1:
                continue
            self.image_paths[index + 1], self.image_paths[index] = (
                self.image_paths[index],
                self.image_paths[index + 1],
            )
        self._update_image_listbox()
        self.image_listbox.selection_clear(0, tk.END)
        for index in selection:
            self.image_listbox.selection_set(min(index + 1, len(self.image_paths) - 1))

    def _clear_images(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self.image_paths.clear()
        self._update_image_listbox()
        self._update_step_flags()
        self._reset_preview()

    def _select_output_path(self) -> None:
        current = self.output_path.get().strip()
        default = Path(current) if current else None
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
            self.output_path.set(file_path)
            self._last_auto_output = None

    # --- 進捗・プレビュー更新 -------------------------------------------
    def _make_progress_callback(self) -> Callable[[int, int, str], None]:
        def _callback(current: int, total: int, message: str) -> None:
            self._notify(lambda: self._handle_progress(current, total, message))

        return _callback

    def _handle_progress(self, current: int, total: int, message: str) -> None:
        if self.progress_bar:
            self.progress_bar.configure(maximum=max(total, 1))
            self.progress_bar.configure(value=min(current, total))
        self.progress_label_var.set(message)
        self.status_var.set(message)
        if not self._ocr_started:
            self.step_vars["ocr"].set(True)
            self._ocr_started = True

    def _make_preview_callback(self) -> Callable[[int, int, Image.Image], None]:
        def _callback(current: int, total: int, image: Image.Image) -> None:
            self._notify(lambda: self._handle_preview(current, total, image.copy()))

        return _callback

    def _handle_preview(self, current: int, total: int, image: Image.Image) -> None:
        preview = image.copy()
        preview.thumbnail(self._preview_max_size, Image.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(preview)
        if self.preview_label:
            self.preview_label.configure(image=self._preview_photo, text="")
        self.preview_info_var.set(f"プレビュー: {current}/{total}ページ")
        if not self._preview_started:
            self.step_vars["layout"].set(True)
            self._preview_started = True

    # --- スレッド制御 ---------------------------------------------------
    def _run_in_thread(self, target: Callable[[], None]) -> None:
        def wrapper() -> None:
            try:
                target()
            finally:
                self._worker = None
                self._cancel_event = None
                self._notify(lambda: self._set_busy(False))

        self._worker = threading.Thread(target=wrapper, daemon=True)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        for widget in (
            self.add_btn,
            self.remove_btn,
            self.up_btn,
            self.down_btn,
            self.clear_list_btn,
            self.convert_btn,
            self.clear_btn,
            self.browse_btn,
        ):
            if widget:
                widget.configure(state=state)
        if self.image_listbox:
            self.image_listbox.configure(state=state)
        if self.cancel_btn:
            self.cancel_btn.configure(state=tk.NORMAL if busy else tk.DISABLED)

    def _cancel_running_task(self) -> None:
        if self._cancel_event and not self._cancel_event.is_set():
            self._cancel_event.set()
            self._log("キャンセル要求を送信しました。")
            self._notify(lambda: self._update_status("キャンセルしています…"))

    # --- ボタン操作 -----------------------------------------------------
    def _start_conversion(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        if not self.image_paths:
            messagebox.showerror("エラー", "入力画像を追加してください。")
            return

        output_path_str = self.output_path.get().strip()
        if not output_path_str:
            messagebox.showerror("エラー", "出力先のPDFファイルを指定してください。")
            return

        output_path = Path(output_path_str)
        if output_path.suffix.lower() != ".pdf":
            messagebox.showerror("エラー", ".pdf拡張子のファイル名を指定してください。")
            return

        self._cancel_event = threading.Event()
        self._reset_steps()
        self._set_busy(True)
        self._reset_progress(len(self.image_paths))
        self._reset_preview()
        self._update_status("画像から検索可能PDFを生成しています…")
        self._log(f"生成を開始: {output_path}")

        image_list = list(self.image_paths)
        self._run_in_thread(
            lambda: self._conversion_task(image_list=image_list, output_path=output_path)
        )

    def _conversion_task(self, image_list: list[Path], output_path: Path) -> None:
        try:
            create_searchable_pdf_from_images(
                image_list,
                output_path,
                progress_callback=self._make_progress_callback(),
                preview_callback=self._make_preview_callback(),
                cancel_event=self._cancel_event,
            )
        except OCRCancelledError:
            self._log("画像からPDFへの変換をキャンセルしました。")
            self._notify(lambda: self._update_status("変換をキャンセルしました。"))
        except (FileNotFoundError, OCRConversionError) as exc:
            message = str(exc)
            self._log(f"エラー: {message}")
            self._handle_failure(message)
        except Exception as exc:  # noqa: BLE001
            self._log(f"予期しないエラー: {exc}")
            self._handle_failure("変換中に予期しないエラーが発生しました。ログを確認してください。")
        else:
            self._log("画像からPDFの変換が完了しました。")

            def _on_success() -> None:
                self.step_vars["save"].set(True)
                self._update_status("変換が完了しました。")
                messagebox.showinfo(
                    "完了", f"検索可能なPDFを保存しました:\n{output_path}"
                )

            self._notify(_on_success)

    # --- ユーティリティ -------------------------------------------------
    def _update_image_listbox(self) -> None:
        if not self.image_listbox:
            return
        self.image_listbox.delete(0, tk.END)
        for index, path in enumerate(self.image_paths, start=1):
            self.image_listbox.insert(tk.END, f"{index:02d}: {path.name}")

    def _suggest_output_path(self) -> None:
        if not self.image_paths:
            return
        first = self.image_paths[0]
        suggested = first.with_name(f"{first.stem}_searchable.pdf")
        current = self.output_path.get().strip()
        if not current or current == str(self._last_auto_output):
            self._suspend_output_trace = True
            self.output_path.set(str(suggested))
            self._suspend_output_trace = False
            self._last_auto_output = suggested

    def _reset_progress(self, total: int) -> None:
        if self.progress_bar:
            self.progress_bar.configure(maximum=max(total, 1), value=0)
        self.progress_label_var.set(f"進捗: 0/{total}ページ")

    def _reset_preview(self) -> None:
        if self.preview_label:
            self.preview_label.configure(image="", text="プレビューはここに表示されます")
        self._preview_photo = None
        self.preview_info_var.set("プレビューはまだありません")
        self._preview_started = False

    def _reset_steps(self) -> None:
        for var in self.step_vars.values():
            var.set(False)
        self.step_vars["select"].set(bool(self.image_paths))
        self._preview_started = False
        self._ocr_started = False

    def _update_step_flags(self) -> None:
        self.step_vars["select"].set(bool(self.image_paths))

    def _update_status(self, message: str) -> None:
        self.status_var.set(message)

    def _log(self, message: str) -> None:
        def append() -> None:
            if not self.log_widget:
                return
            self.log_widget.configure(state=tk.NORMAL)
            self.log_widget.insert(tk.END, message + "\n")
            self.log_widget.see(tk.END)
            self.log_widget.configure(state=tk.DISABLED)

        self._notify(append)

    def _clear_workspace(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self.image_paths.clear()
        self._suspend_output_trace = True
        self.output_path.set("")
        self._suspend_output_trace = False
        self._last_auto_output = None
        self._reset_steps()
        self._reset_progress(0)
        self._reset_preview()
        self._clear_log()
        self._update_status("準備完了")

    def _clear_log(self) -> None:
        if not self.log_widget:
            return
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state=tk.DISABLED)

    def _notify(self, callback: Callable[[], None]) -> None:
        def safe_callback() -> None:
            if self.frame.winfo_exists():
                callback()

        self.root.after(0, safe_callback)

    def _handle_failure(self, message: str) -> None:
        def _show() -> None:
            messagebox.showerror("エラー", message)
            self._update_status("エラーが発生しました。内容を確認してください。")

        self._notify(_show)

    def _on_output_path_changed(self) -> None:
        if self._suspend_output_trace:
            return
        value = self.output_path.get().strip()
        if value and self._last_auto_output and value == str(self._last_auto_output):
            return
        self._last_auto_output = None


class OCRDesktopApp:
    """画像PDFを処理する簡易デスクトップアプリケーション。"""

    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.master.title("Image PDF OCR Suite")
        self.single_geometry = "720x520"
        self.geometry_map: dict[int, str] = {
            1: self.single_geometry,
            2: "1420x520",
            4: "1420x980",
        }
        self.master.geometry(self.single_geometry)

        self.master.report_callback_exception = self._handle_ui_exception

        self.mode_options: dict[str, int] = {
            "1つの作業": 1,
            "2つの作業": 2,
            "4つの作業": 4,
        }
        self.mode_var = tk.StringVar(value="1つの作業")
        self.workspaces: list[ProcessingWorkspace] = []
        self.current_workspace_count = 1

        self.notebook: ttk.Notebook | None = None
        self.ocr_tab: tk.Frame | None = None
        self.image_tab: tk.Frame | None = None
        self.password_tab: tk.Frame | None = None
        self.password_workspace: PDFPasswordRemovalWorkspace | None = None
        self.image_workspace: ImagesToPDFWorkspace | None = None
        self.image_tab_geometry = "1100x720"

        self._create_widgets()
        self._rebuild_workspaces(1)

    def _create_widgets(self) -> None:
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.ocr_tab = tk.Frame(self.notebook)
        self.notebook.add(self.ocr_tab, text="OCR処理")

        control_frame = tk.Frame(self.ocr_tab)
        control_frame.pack(fill=tk.X, padx=12, pady=(12, 0))

        mode_label = tk.Label(control_frame, text="同時に処理する作業数:")
        mode_label.pack(side=tk.LEFT)

        mode_combo = ttk.Combobox(
            control_frame,
            state="readonly",
            values=tuple(self.mode_options.keys()),
            width=15,
            textvariable=self.mode_var,
        )
        mode_combo.pack(side=tk.LEFT, padx=(8, 0))
        mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_mode_change())

        self.workspace_container = tk.Frame(self.ocr_tab)
        self.workspace_container.pack(fill=tk.BOTH, expand=True)

        self.image_tab = tk.Frame(self.notebook)
        self.notebook.add(self.image_tab, text="画像からPDF")

        self.image_workspace = ImagesToPDFWorkspace(self, self.image_tab)
        self.image_workspace.pack(fill=tk.BOTH, expand=True, padx=(12, 12), pady=(12, 12))

        self.password_tab = tk.Frame(self.notebook)
        self.notebook.add(self.password_tab, text="PDFパスワード解除")

        self.password_workspace = PDFPasswordRemovalWorkspace(self, self.password_tab)
        self.password_workspace.pack(
            fill=tk.BOTH, expand=True, padx=(12, 12), pady=(12, 12)
        )

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_mode_change(self) -> None:
        count = self.mode_options.get(self.mode_var.get(), 1)
        self._rebuild_workspaces(count)

    def _rebuild_workspaces(self, count: int) -> None:
        for workspace in self.workspaces:
            workspace.prepare_for_destroy()
            workspace.destroy()
        self.workspaces.clear()

        for child in self.workspace_container.winfo_children():
            child.destroy()

        self.current_workspace_count = count
        if self._is_ocr_tab_selected():
            self._apply_geometry(count)

        positions = self._resolve_layout_positions(count)
        if not positions:
            return

        max_row = max(row for row, _col in positions)
        max_col = max(col for _row, col in positions)

        for row in range(max_row + 1):
            self.workspace_container.grid_rowconfigure(row, weight=1)
        for col in range(max_col + 1):
            self.workspace_container.grid_columnconfigure(col, weight=1)

        for row, col in positions:
            workspace = ProcessingWorkspace(self, self.workspace_container)
            padx = (
                12 if col == 0 else 6,
                12 if col == max_col else 6,
            )
            pady = (
                12 if row == 0 else 6,
                12 if row == max_row else 6,
            )
            workspace.grid(row=row, column=col, padx=padx, pady=pady, sticky="nsew")
            self.workspaces.append(workspace)

    def _handle_ui_exception(self, exc_type, exc_value, exc_traceback) -> None:  # type: ignore[override]
        message = f"UIエラー: {exc_value}"
        for workspace in self.workspaces:
            workspace._log(message)
            workspace._update_status("UIで予期しないエラーが発生しました。ログをご確認ください。")
        messagebox.showerror("UIエラー", "予期しないUIエラーが発生しました。ログを確認してください。")

    def _on_tab_changed(self, _event: object | None = None) -> None:
        if self._is_ocr_tab_selected():
            self._apply_geometry(self.current_workspace_count)
        elif self._is_image_tab_selected():
            self.master.geometry(self.image_tab_geometry)
        else:
            self.master.geometry(self.single_geometry)

    def _apply_geometry(self, count: int) -> None:
        if count in self.geometry_map:
            self.master.geometry(self.geometry_map[count])
            return

        max_key = max(self.geometry_map)
        self.master.geometry(self.geometry_map[max_key])

    def _is_ocr_tab_selected(self) -> bool:
        if not self.notebook or not self.ocr_tab:
            return True
        return self.notebook.select() == str(self.ocr_tab)

    def _is_image_tab_selected(self) -> bool:
        if not self.notebook or not self.image_tab:
            return False
        return self.notebook.select() == str(self.image_tab)

    def _resolve_layout_positions(self, count: int) -> list[tuple[int, int]]:
        if count <= 1:
            return [(0, 0)]
        if count == 2:
            return [(0, 0), (0, 1)]
        if count == 4:
            return [(0, 0), (0, 1), (1, 0), (1, 1)]

        return [(0, index) for index in range(count)]


def main() -> None:
    root = tk.Tk()
    app = OCRDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
