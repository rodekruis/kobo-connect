from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from utils.cosmos import add_submission, update_submission_status
from utils.utilsKobo import clean_kobo_data
from utils.logger import logger
from clients.bitrix24_api_client import Bitrix24
import os

router = APIRouter()

@router.post("/kobo-to-bitrix24", tags=["Bitrix24"])
async def kobo_to_bitrix24(request: Request):
    """Receive Kobo submission and send to Bitrix24 using custom header mapping."""

    # Step 1: Parse Kobo submission
    try:
        kobo_data = await request.json()
        extra_logs = {
            "environment": os.getenv("ENV"),
            "kobo_form_id": str(kobo_data.get("_xform_id_string", "")),
            "kobo_form_version": str(kobo_data.get("__version__", "")),
            "kobo_submission_id": str(kobo_data.get("_id", "")),
        }
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body from Kobo")

    kobo_data = clean_kobo_data(kobo_data)

    # Step 2: Check for duplicates
    submission = add_submission(kobo_data)
    if submission["status"] == "success":
        return JSONResponse(
            status_code=200,
            content={"detail": "Submission has already been successfully processed"},
        )

    # Step 3: Read headers
    headers = request.headers
    target_url = headers.get("targeturl")
    target_key = headers.get("targetkey")
    entity_type_id = headers.get("entitytypeid")

    if not target_url or not target_key or not entity_type_id:
        raise HTTPException(
            status_code=400,
            detail="Missing required headers: 'targeturl', 'targetkey', or 'entitytypeid'",
        )

    try:
        entity_type_id = int(entity_type_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="'entitytypeid' must be an integer")

    # Step 4: Build Bitrix fields (with multi/repeat logic)
    fields = {}
    RESERVED = {"targeturl", "targetkey", "entitytypeid", "host", "content-length", "content-type", "user-agent", "accept", "accept-encoding", "connection"}

    for kobo_field, bitrix_field in headers.items():
        if kobo_field.lower() in RESERVED:
            continue

        multi = False
        repeat = False
        repeat_no = 0
        repeat_question = ""

        # handle multi: prefix
        if "multi:" in kobo_field:
            kobo_field = kobo_field.split("multi:")[1]
            multi = True

        # handle repeat: prefix
        elif "repeat:" in kobo_field:
            parts = kobo_field.split(":")
            if len(parts) >= 4:
                _, field, index, subfield = parts
                kobo_field = field
                repeat_no = int(index)
                repeat_question = subfield
                repeat = True

        if kobo_field not in kobo_data:
            continue

        # Value extraction
        if multi:
            kobo_value = kobo_data[kobo_field].split(" ")
        elif repeat:
            if isinstance(kobo_data[kobo_field], list) and 0 <= repeat_no < len(kobo_data[kobo_field]):
                cleaned = clean_kobo_data(kobo_data[kobo_field][repeat_no])
                if repeat_question in cleaned:
                    kobo_value = cleaned[repeat_question]
                else:
                    continue
            else:
                continue
        else:
            kobo_value = kobo_data[kobo_field]

        # parse target field name if it includes colons
        if ":" in bitrix_field:
            _, bitrix_field = bitrix_field.split(":", 1)

        fields[bitrix_field] = kobo_value

    if not fields:
        raise HTTPException(status_code=400, detail="No mapped fields found in Kobo submission")

    # Step 5: Send to Bitrix
    payload = {
        "entityTypeId": entity_type_id,
        "fields": fields,
    }

    client = Bitrix24(target_url, target_key)
    response = client.request(
        "POST",
        "crm.item.add.json",
        submission,
        params=payload,
        logs=extra_logs,
    )

    if "result" not in response:
        error_message = response.content.decode("utf-8")
        logger.error(f"Bitrix request failed: {error_message}", extra=extra_logs)
        update_submission_status(submission, "failed", error_message)
        raise HTTPException(status_code=500, detail="Bitrix24 rejected the request")

    logger.info("Bitrix submission successful", extra=extra_logs)
    update_submission_status(submission, "success")
    return JSONResponse(status_code=200, content=response)
