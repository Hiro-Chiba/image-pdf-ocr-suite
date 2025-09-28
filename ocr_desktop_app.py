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
    extract_text_to_file,
    remove_pdf_password,
)


class ProcessingWorkspace:
    """単一のOCR処理画面を構築・管理する。"""

    def __init__(self, app: "OCRDesktopApp", parent: tk.Widget) -> None:
        self.root = app.master
        self.frame = tk.Frame(parent)

        self.input_path = tk.StringVar()
        self.output_pdf_path = tk.StringVar()
        self.output_text_path = tk.StringVar()
        self.status_var = tk.StringVar(value="準備完了")

        self.convert_btn: tk.Button | None = None
        self.extract_btn: tk.Button | None = None
        self.cancel_btn: tk.Button | None = None
        self.log_widget: ScrolledText | None = None
        self.progress: ttk.Progressbar | None = None

        self._worker: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None

        self._create_widgets()

    # --- ライフサイクル -------------------------------------------------
    def pack(self, *, side: str, padx: tuple[int, int], pady: tuple[int, int]) -> None:
        self.frame.pack(side=side, fill=tk.BOTH, expand=True, padx=padx, pady=pady)

    def prepare_for_destroy(self) -> None:
        self._cancel_running_task()
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=0.1)

    def destroy(self) -> None:
        self.frame.destroy()

    # --- UI構築 ---------------------------------------------------------
    def _create_widgets(self) -> None:
        input_frame = tk.LabelFrame(self.frame, text="入力PDF")
        input_frame.pack(fill=tk.X, padx=12, pady=(12, 6))

        input_entry = tk.Entry(input_frame, textvariable=self.input_path)
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_input_btn = tk.Button(
            input_frame, text="参照", width=10, command=self._select_input_file
        )
        browse_input_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        output_pdf_frame = tk.LabelFrame(self.frame, text="検索可能PDFの出力先")
        output_pdf_frame.pack(fill=tk.X, padx=12, pady=6)

        output_pdf_entry = tk.Entry(output_pdf_frame, textvariable=self.output_pdf_path)
        output_pdf_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_output_pdf_btn = tk.Button(
            output_pdf_frame,
            text="保存先",
            width=10,
            command=self._select_output_pdf,
        )
        browse_output_pdf_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        output_text_frame = tk.LabelFrame(self.frame, text="抽出テキストの保存先")
        output_text_frame.pack(fill=tk.X, padx=12, pady=6)

        output_text_entry = tk.Entry(output_text_frame, textvariable=self.output_text_path)
        output_text_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_output_text_btn = tk.Button(
            output_text_frame,
            text="保存先",
            width=10,
            command=self._select_output_text,
        )
        browse_output_text_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        button_frame = tk.Frame(self.frame)
        button_frame.pack(fill=tk.X, padx=12, pady=(6, 0))

        self.convert_btn = tk.Button(
            button_frame, text="検索可能PDFを作成", command=self._start_conversion
        )
        self.convert_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.extract_btn = tk.Button(
            button_frame, text="テキストを抽出", command=self._start_extraction
        )
        self.extract_btn.pack(side=tk.LEFT, padx=6)

        self.cancel_btn = tk.Button(
            button_frame, text="キャンセル", state=tk.DISABLED, command=self._cancel_running_task
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=6)

        clear_btn = tk.Button(button_frame, text="ログをクリア", command=self._clear_log)
        clear_btn.pack(side=tk.LEFT, padx=6)

        self.log_widget = ScrolledText(self.frame, height=16, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 6))

        status_frame = tk.Frame(self.frame)
        status_frame.pack(fill=tk.X, padx=12, pady=(0, 12))

        self.progress = ttk.Progressbar(status_frame, mode="indeterminate")
        self.progress.pack(side=tk.LEFT, padx=(0, 12), pady=4)

        status_label = tk.Label(status_frame, textvariable=self.status_var, anchor=tk.W)
        status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

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
        if self.convert_btn and self.extract_btn and self.cancel_btn and self.progress:
            state = tk.DISABLED if busy else tk.NORMAL
            self.convert_btn.configure(state=state)
            self.extract_btn.configure(state=state)
            self.cancel_btn.configure(state=tk.NORMAL if busy else tk.DISABLED)
            if busy:
                self.progress.start(10)
            else:
                self.progress.stop()

    def _cancel_running_task(self) -> None:
        if self._cancel_event and not self._cancel_event.is_set():
            self._cancel_event.set()
            self._log("キャンセル要求を送信しました。")
            self._notify(lambda: self._update_status("キャンセルしています…"))

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

    # --- ユーティリティ -------------------------------------------------
    def _suggest_output_paths(self, input_path: Path) -> None:
        stem = input_path.stem
        parent = input_path.parent
        if not self.output_pdf_path.get():
            self.output_pdf_path.set(str(parent / f"{stem}_searchable.pdf"))
        if not self.output_text_path.get():
            self.output_text_path.set(str(parent / f"{stem}_text.txt"))

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

        self._notify(append)

    def _show_error(self, message: str) -> None:
        messagebox.showerror("エラー", message)

    def _clear_log(self) -> None:
        if not self.log_widget:
            return
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state=tk.DISABLED)


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
        self.progress: ttk.Progressbar | None = None

        self._worker: threading.Thread | None = None

        self._create_widgets()

    def pack(self, *, fill: str, expand: bool, padx: tuple[int, int], pady: tuple[int, int]) -> None:
        self.frame.pack(fill=fill, expand=expand, padx=padx, pady=pady)

    def _create_widgets(self) -> None:
        input_frame = tk.LabelFrame(self.frame, text="入力PDF")
        input_frame.pack(fill=tk.X, padx=12, pady=(12, 6))

        input_entry = tk.Entry(input_frame, textvariable=self.input_path)
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_input_btn = tk.Button(
            input_frame, text="参照", width=10, command=self._select_input_file
        )
        browse_input_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        password_frame = tk.LabelFrame(self.frame, text="PDFパスワード")
        password_frame.pack(fill=tk.X, padx=12, pady=6)

        password_label = tk.Label(password_frame, text="パスワードを入力してください。")
        password_label.pack(anchor=tk.W, padx=12, pady=(8, 0))

        password_entry = tk.Entry(password_frame, textvariable=self.password, show="*")
        password_entry.pack(fill=tk.X, padx=12, pady=(4, 8))

        output_frame = tk.LabelFrame(self.frame, text="パスワード解除後の保存先")
        output_frame.pack(fill=tk.X, padx=12, pady=6)

        output_entry = tk.Entry(output_frame, textvariable=self.output_path)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 6), pady=8)

        browse_output_btn = tk.Button(
            output_frame, text="保存先", width=10, command=self._select_output_file
        )
        browse_output_btn.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        button_frame = tk.Frame(self.frame)
        button_frame.pack(fill=tk.X, padx=12, pady=(6, 0))

        self.remove_btn = tk.Button(
            button_frame, text="パスワードを解除", command=self._start_removal
        )
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 6))

        status_frame = tk.Frame(self.frame)
        status_frame.pack(fill=tk.X, padx=12, pady=(12, 12))

        self.progress = ttk.Progressbar(status_frame, mode="indeterminate")
        self.progress.pack(side=tk.LEFT, padx=(0, 12), pady=4)

        status_label = tk.Label(status_frame, textvariable=self.status_var, anchor=tk.W)
        status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

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

    def _start_removal(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        input_value = self.input_path.get().strip()
        if not input_value:
            self._show_error("入力PDFを選択してください。")
            return
        input_path = Path(input_value)
        if not input_path.exists():
            self._show_error("指定された入力PDFが見つかりません。")
            return

        output_value = self.output_path.get().strip()
        if not output_value:
            self._show_error("保存先を指定してください。")
            return
        output_path = Path(output_value)
        if output_path.suffix.lower() != ".pdf":
            self._show_error("保存先には.pdf拡張子を指定してください。")
            return

        password = self.password.get()
        if not password:
            self._show_error("パスワードを入力してください。")
            return

        self._set_busy(True)
        self._update_status("パスワードを解除しています…")
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
            self._notify(
                lambda: (
                    messagebox.showinfo(
                        "完了", f"パスワードを解除したPDFを保存しました:\n{output_path}"
                    ),
                    self._update_status("パスワードの解除が完了しました。"),
                )
            )

    def _handle_failure(self, message: str) -> None:
        self._show_error(message)
        self._update_status("エラーが発生しました。内容を確認してください。")

    def _set_busy(self, busy: bool) -> None:
        if not self.remove_btn or not self.progress:
            return
        state = tk.DISABLED if busy else tk.NORMAL
        self.remove_btn.configure(state=state)
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


class OCRDesktopApp:
    """画像PDFを処理する簡易デスクトップアプリケーション。"""

    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.master.title("Image PDF OCR Suite")
        self.single_geometry = "720x520"
        self.double_geometry = "1420x520"
        self.master.geometry(self.single_geometry)

        self.master.report_callback_exception = self._handle_ui_exception

        self.mode_var = tk.StringVar(value="1つの作業")
        self.workspaces: list[ProcessingWorkspace] = []
        self.current_workspace_count = 1

        self.notebook: ttk.Notebook | None = None
        self.ocr_tab: tk.Frame | None = None
        self.password_tab: tk.Frame | None = None
        self.password_workspace: PDFPasswordRemovalWorkspace | None = None

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
            values=("1つの作業", "2つの作業"),
            width=15,
            textvariable=self.mode_var,
        )
        mode_combo.pack(side=tk.LEFT, padx=(8, 0))
        mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_mode_change())

        self.workspace_container = tk.Frame(self.ocr_tab)
        self.workspace_container.pack(fill=tk.BOTH, expand=True)

        self.password_tab = tk.Frame(self.notebook)
        self.notebook.add(self.password_tab, text="PDFパスワード解除")

        self.password_workspace = PDFPasswordRemovalWorkspace(self, self.password_tab)
        self.password_workspace.pack(
            fill=tk.BOTH, expand=True, padx=(12, 12), pady=(12, 12)
        )

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_mode_change(self) -> None:
        count = 2 if self.mode_var.get().startswith("2") else 1
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

        for index in range(count):
            workspace = ProcessingWorkspace(self, self.workspace_container)
            pad_left = 12 if index == 0 else 6
            pad_right = 12 if index == count - 1 else 6
            workspace.pack(side=tk.LEFT, padx=(pad_left, pad_right), pady=(12, 12))
            self.workspaces.append(workspace)

            if count == 2 and index == 0:
                separator = ttk.Separator(self.workspace_container, orient=tk.VERTICAL)
                separator.pack(side=tk.LEFT, fill=tk.Y)

    def _handle_ui_exception(self, exc_type, exc_value, exc_traceback) -> None:  # type: ignore[override]
        message = f"UIエラー: {exc_value}"
        for workspace in self.workspaces:
            workspace._log(message)
            workspace._update_status("UIで予期しないエラーが発生しました。ログをご確認ください。")
        messagebox.showerror("UIエラー", "予期しないUIエラーが発生しました。ログを確認してください。")

    def _on_tab_changed(self, _event: object | None = None) -> None:
        if self._is_ocr_tab_selected():
            self._apply_geometry(self.current_workspace_count)
        else:
            self.master.geometry(self.single_geometry)

    def _apply_geometry(self, count: int) -> None:
        if count >= 2:
            self.master.geometry(self.double_geometry)
        else:
            self.master.geometry(self.single_geometry)

    def _is_ocr_tab_selected(self) -> bool:
        if not self.notebook or not self.ocr_tab:
            return True
        return self.notebook.select() == str(self.ocr_tab)


def main() -> None:
    root = tk.Tk()
    app = OCRDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
