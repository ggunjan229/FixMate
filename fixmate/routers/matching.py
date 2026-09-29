"""Compatibility route for evaluating the saved allocation model on candidates."""
from fastapi import APIRouter, HTTPException

from fixmate.services.matching import rank_candidate_payload

router = APIRouter()


@router.post("/rank-candidates")
def rank_candidates(payload: dict):
    try:
        return rank_candidate_payload(payload)
    except FileNotFoundError as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(422, f"Could not score candidates: {error}") from error
