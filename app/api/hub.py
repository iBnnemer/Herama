"""Hugging Face model search and downloads."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import hub

router = APIRouter(prefix="/api/hub")


class DownloadReq(BaseModel):
    repo: str
    file: str
    size: int = 0


def _upstream(e: Exception) -> HTTPException:
    return HTTPException(502, f"Hugging Face request failed: {e}")


@router.get("/hardware")
def hardware():
    return hub.hardware()


@router.get("/search")
def search(q: str = "", moe: bool = False, uncensored: bool = False):
    try:
        return hub.search(q, moe, uncensored)
    except Exception as e:
        raise _upstream(e)


@router.get("/files")
def files(repo: str):
    try:
        return {"hardware": hub.hardware(), "files": hub.files(repo)}
    except Exception as e:
        raise _upstream(e)


@router.post("/download")
def download(req: DownloadReq):
    try:
        return hub.start_download(req.repo, req.file, req.size)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/downloads")
def downloads():
    return hub.downloads()


@router.delete("/downloads/{job_id}")
def cancel(job_id: str):
    if not hub.cancel_download(job_id):
        raise HTTPException(404, "unknown download")
    return {"ok": True}
