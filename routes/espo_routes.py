from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from utils.kobo_utils import (
    add_submission,
    clean_kobo_data,
    get_attachment_dict,
    update_submission_status,
    espo_request,
    required_headers_espocrm,
    required_headers_121,
    login121,
)
from utils.espo_utils import espo_request, required_headers_espocrm
import logging
import os

router = APIRouter()

@router.post("/kobo-to-espocrm")
async def kobo_to_espocrm(
    request: Request, dependencies=Depends(required_headers_espocrm)
):
    """Send a Kobo submission to EspoCRM."""
    # ... existing code ...
    return JSONResponse(status_code=200, content=target_response)

@router.post("/kobo-to-121")
async def kobo_to_121(request: Request, dependencies=Depends(required_headers_121)):
    """Send a Kobo submission to 121."""
    # ... existing code ...
    return JSONResponse(status_code=import_response.status_code, content=import_response_message)
