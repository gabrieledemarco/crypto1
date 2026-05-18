"""
/vibe router — Claude proxy (stub for M2, full in M5)
"""
from fastapi import APIRouter
from api.models import VibeGenerateRequest

router = APIRouter()


@router.post("/generate")
def vibe_generate(body: VibeGenerateRequest):
    return {
        "status": "stub",
        "message": "Vibe Trading will be implemented in M5",
        "strategy": {}
    }


@router.post("/improve")
def vibe_improve(body: dict):
    return {"status": "stub"}
