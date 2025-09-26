import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";

interface ConversionState {
  status: "idle" | "uploading" | "converting" | "completed" | "error";
  message?: string;
}

const API_ENDPOINT = import.meta.env.VITE_API_URL ?? "/api/convert";

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [convertedPdfUrl, setConvertedPdfUrl] = useState<string | null>(null);
  const [state, setState] = useState<ConversionState>({ status: "idle" });

  const isProcessing = state.status === "uploading" || state.status === "converting";

  const handleFileChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (convertedPdfUrl) {
      URL.revokeObjectURL(convertedPdfUrl);
    }
    setConvertedPdfUrl(null);
    if (file) {
      setSelectedFile(file);
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
    } else {
      setSelectedFile(null);
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
      setPreviewUrl(null);
    }
  }, [convertedPdfUrl, previewUrl]);

  const handleConvert = useCallback(async () => {
    if (!selectedFile) {
      setState({ status: "error", message: "PDFファイルを選択してください。" });
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    setState({ status: "uploading", message: "アップロード中..." });

    try {
      const response = await axios.post<ArrayBuffer>(API_ENDPOINT, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        responseType: "arraybuffer",
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentage = Math.round((progressEvent.loaded / progressEvent.total) * 100);
            setState({ status: "uploading", message: `アップロード中... ${percentage}%` });
          }
        },
      });

      setState({ status: "converting", message: "変換結果を処理しています..." });

      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      setConvertedPdfUrl(url);
      setState({ status: "completed", message: "変換が完了しました。" });
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        const message = error.response?.data?.detail ?? "変換に失敗しました。";
        setState({ status: "error", message });
      } else {
        setState({ status: "error", message: "予期せぬエラーが発生しました。" });
      }
    }
  }, [selectedFile]);

  const reset = useCallback(() => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    if (convertedPdfUrl) {
      URL.revokeObjectURL(convertedPdfUrl);
    }
    setSelectedFile(null);
    setPreviewUrl(null);
    setConvertedPdfUrl(null);
    setState({ status: "idle" });
  }, [previewUrl, convertedPdfUrl]);

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
      if (convertedPdfUrl) {
        URL.revokeObjectURL(convertedPdfUrl);
      }
    };
  }, [previewUrl, convertedPdfUrl]);

  const statusMessage = useMemo(() => state.message, [state]);

  return (
    <div className="container">
      <header className="header">
        <h1>Image PDF OCR Suite</h1>
        <p>OCRで画像ベースのPDFを検索可能なPDFに変換します。</p>
      </header>

      <section className="controls">
        <label className="file-input">
          <span>PDFを選択</span>
          <input type="file" accept="application/pdf" onChange={handleFileChange} disabled={isProcessing} />
        </label>

        <div className="button-group">
          <button className="primary" onClick={handleConvert} disabled={isProcessing || !selectedFile}>
            {isProcessing ? "変換中..." : "変換する"}
          </button>
          <button className="secondary" onClick={reset} disabled={isProcessing && !convertedPdfUrl}>
            リセット
          </button>
        </div>

        {statusMessage && <p className={`status ${state.status}`}>{statusMessage}</p>}
      </section>

      <section className="preview-grid">
        <div className="preview">
          <h2>アップロードしたPDF</h2>
          {previewUrl ? (
            <object data={previewUrl} type="application/pdf" aria-label="original pdf preview">
              <p>プレビューを表示できません。ファイルをダウンロードしてご確認ください。</p>
            </object>
          ) : (
            <p className="placeholder">PDFをアップロードするとプレビューが表示されます。</p>
          )}
        </div>

        <div className="preview">
          <h2>変換後のPDF</h2>
          {convertedPdfUrl ? (
            <>
              <object data={convertedPdfUrl} type="application/pdf" aria-label="converted pdf preview">
                <p>プレビューを表示できません。ファイルをダウンロードしてご確認ください。</p>
              </object>
              <a className="download" href={convertedPdfUrl} download>
                変換結果をダウンロード
              </a>
            </>
          ) : (
            <p className="placeholder">変換後のPDFプレビューがここに表示されます。</p>
          )}
        </div>
      </section>
    </div>
  );
}

export default App;
