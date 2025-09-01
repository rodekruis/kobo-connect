from fastapi import APIRouter, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from utils.cosmos import add_submission, update_submission_status
from utils.utilsKobo import (
    clean_kobo_data,
    get_attachment_dict,
    get_kobo_attachment,
)
from utils.logger import logger
from clients.bitrix24_api_client import Bitrix24
import os
import re
import base64

router = APIRouter()


def required_headers_bitrix24(targeturl: str = Header()):
    return targeturl


@router.post("/kobo-to-bitrix24", tags=["Bitrix24"])
async def kobo_to_bitrix24(
    request: Request, dependencies=Depends(required_headers_bitrix24)
):
    """Send a Kobo submission to Bitrix24."""

    kobo_data = await request.json()
    kobo_data["formhub/uuid"] = kobo_data.get("_uuid", "")
    extra_logs = {"environment": os.getenv("ENV")}
    try:
        extra_logs["kobo_form_id"] = str(kobo_data["_xform_id_string"])
        extra_logs["kobo_form_version"] = str(kobo_data["__version__"])
        extra_logs["kobo_submission_id"] = str(kobo_data["_id"])
    except KeyError:
        raise HTTPException(status_code=422, detail="Not a valid Kobo submission")
    kobo_data = clean_kobo_data(kobo_data)

    target_response = {}

    # store the kobo submission uuid and status in cosmos, to avoid duplicate submissions
    if "formhub/uuid" not in kobo_data:
        kobo_data["formhub/uuid"] = kobo_data["_uuid"]

    submission = add_submission(kobo_data)
    if submission["status"] == "success":
        return JSONResponse(
            status_code=200,
            content={"detail": "Submission has already been successfully processed"},
        )

    # initialize Bitrix24 API client
    client = Bitrix24(request.headers["targeturl"], request.headers["targetkey"])

    # --- Begin SPA logic ---
    payload = {"fields": {}}

    # Read entityTypeId from header (required for SPA)
    if "entitytypeid" in request.headers:
        payload["entityTypeId"] = int(request.headers["entitytypeid"])
        target_entity = "crm.item.add.json"
    else:
        error_message = "Missing entityTypeId in headers for SPA"
        logger.error(f"Failed: {error_message}", extra=extra_logs)
        update_submission_status(submission, "failed", error_message)

    # Loop through headers to map Kobo data to Bitrix24 fields
    for kobo_field, target_field in request.headers.items():
        if kobo_field.lower() in ["targeturl", "targetkey", "entitytypeid"]:
            continue

        multi = False
        repeat, repeat_no, repeat_question = False, 0, ""

        if "multi:" in kobo_field:
            kobo_field = kobo_field.split(":")[1]
            multi = True
        if "repeat:" in kobo_field:
            split = kobo_field.split(":")
            kobo_field = split[1]
            repeat_no = int(split[2])
            repeat_question = split[3]
            repeat = True

        if kobo_field not in kobo_data.keys():
            continue

        if multi:
            kobo_value = kobo_data[kobo_field].split(" ")
        elif repeat:
            if 0 <= repeat_no < len(kobo_data[kobo_field]):
                kobo_data[kobo_field][repeat_no] = clean_kobo_data(
                    kobo_data[kobo_field][repeat_no]
                )
                if repeat_question not in kobo_data[kobo_field][repeat_no].keys():
                    continue
                kobo_value = kobo_data[kobo_field][repeat_no][repeat_question]
            else:
                continue
        else:
            kobo_value = kobo_data[kobo_field]

        payload["fields"][target_field] = kobo_value

    if len(payload["fields"]) == 0:
        error_message = "No fields found in submission or no mappings found in headers"
        logger.error(f"Failed: {error_message}", extra=extra_logs)
        update_submission_status(submission, "failed", error_message)

    # Send to Bitrix24
    response = client.request(
        "POST",
        target_entity,
        submission,
        params=payload,
        logs=extra_logs,
    )

    if "result" not in response.keys():
        error_message = response.content.decode("utf-8")
        logger.error(f"Failed: {error_message}", extra=extra_logs)
        update_submission_status(submission, "failed", error_message)
    else:
        target_response[target_entity] = response

    logger.info("Success", extra=extra_logs)
    update_submission_status(submission, "success")
    return JSONResponse(status_code=200, content=target_response)
