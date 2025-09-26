from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from image_pdf_ocr import OCRConversionError, create_searchable_pdf

app = FastAPI(title="Image PDF OCR Suite", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/convert")
async def convert_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> FileResponse:
    if file.content_type not in {"application/pdf"}:
        raise HTTPException(status_code=400, detail="PDFファイルをアップロードしてください。")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as input_tmp:
            input_tmp.write(await file.read())
            input_path = Path(input_tmp.name)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as output_tmp:
            output_path = Path(output_tmp.name)

        create_searchable_pdf(input_path, output_path)

        background_tasks.add_task(input_path.unlink, missing_ok=True)
        background_tasks.add_task(output_path.unlink, missing_ok=True)

        return FileResponse(
            path=output_path,
            filename=f"searchable_{file.filename or 'document'}.pdf",
            media_type="application/pdf",
            background=background_tasks,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OCRConversionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
