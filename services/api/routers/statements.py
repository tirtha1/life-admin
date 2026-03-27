"""
Statement upload router backed by the shared statement analysis engine.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.statement import StatementAnalysisResponse
from app.services.statement_analysis import analyze_statement_file

router = APIRouter(prefix="/statements", tags=["statements"])


@router.post("/analyze", response_model=StatementAnalysisResponse)
async def analyze_statement(file: UploadFile = File(...)):
    filename = file.filename or "statement"
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if extension not in {"csv", "pdf"}:
        raise HTTPException(status_code=400, detail="Upload a CSV or PDF bank statement.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        return await analyze_statement_file(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
