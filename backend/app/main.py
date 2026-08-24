from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.models.analysis_result import AnalyzeRequest, AnalyzeResponse, ReviewUpdate
from app.services.pipeline import AnalysisPipeline
from app.services.review import update_review


app = FastAPI(
    title="AI Repository Intelligence POC",
    description="Generic GitHub repository → business rules → BRD using Amazon Bedrock",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    try:
        result = AnalysisPipeline().run(
            repo_url=request.repo_url,
            branch=request.branch,
            module_hints=request.module_hints,
            upload_source=request.upload_source,
        )
        return AnalyzeResponse(
            run_id=result["run_id"],
            status=result["status"],
            summary=result["summary"],
            artifacts=result["artifacts"],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}/review")
def get_review(run_id: str):
    path = settings.output_dir / run_id / "review.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run/review not found")
    return path.read_text(encoding="utf-8")


@app.get("/api/download/{run_id}")
def download_brd(run_id: str):
    path = settings.output_dir / run_id / "BRD.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="BRD not found for this run")
    return FileResponse(path, media_type="application/pdf", filename="BRD.pdf")


