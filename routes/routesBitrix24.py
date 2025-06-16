from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from utils.utilsKobo import (
    add_submission,
    clean_kobo_data,
    get_attachment_dict,
    get_kobo_attachment,
    update_submission_status,
)
from utils.logger import logger
from clients.bitrix24_api_client import Bitrix24
import os
import re
import base64

router = APIRouter()


@router.post("/kobo-to-bitrix24", tags=["Bitrix24"])
async def kobo_to_bitrix24(request: Request):
    """Send a Kobo submission to Bitrix24."""

    kobo_data = await request.json()
    extra_logs = {"environment": os.getenv("ENV")}
    try:
        extra_logs["kobo_form_id"] = str(kobo_data["_xform_id_string"])
        extra_logs["kobo_form_version"] = str(kobo_data["__version__"])
        extra_logs["kobo_submission_id"] = str(kobo_data["_id"])
    except KeyError:
        raise HTTPException(status_code=422, detail="Not a valid Kobo submission")

    logger.info("Succesfully received submission from Kobo", extra=extra_logs)

    target_response = {}

    # store the submission uuid and status, to avoid duplicate submissions
    submission = add_submission(kobo_data)
    logger.info(
        "Succesfully created/retrieved submission from Cosmos DB", extra=extra_logs
    )

    if submission["status"] == "success":
        logger.info(
            "Submission has already been successfully processed", extra=extra_logs
        )
        return JSONResponse(
            status_code=200,
            content={"detail": "Submission has already been successfully processed"},
        )

    kobo_data = clean_kobo_data(kobo_data)

    # Create API payload body
    payload, target_entity = {}, ""
    for kobo_field, target_field in request.headers.items():

        multi = False
        repeat, repeat_no, repeat_question = False, 0, ""

        # determine if kobo_field is of type multi or repeat
        if "multi." in kobo_field:
            kobo_field = kobo_field.split(".")[1]
            multi = True
        if "repeat." in kobo_field:
            split = kobo_field.split(".")
            kobo_field = split[1]
            repeat_no = int(split[2])
            repeat_question = split[3]
            repeat = True

        # check if kobo_field is in kobo_data
        if kobo_field not in kobo_data.keys():
            continue

        # check if entity is nested in target_field
        if len(target_field.split(".")) == 2:
            target_entity = target_field.split(".")[0]
            target_field = target_field.split(".")[1]
            if target_entity not in payload.keys():
                payload[target_entity] = {}
        else:
            continue

        # get kobo_value based on kobo_field type
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

        payload[target_entity][target_field] = kobo_value

    if len(payload) == 0:
        error_message = "No fields found in submission or no entities found in headers"
        logger.error(f"Failed: {error_message}", extra=extra_logs)
        update_submission_status(submission, "failed", error_message)

    for target_entity in payload.keys():

        bitrix24_url = None
        if f"bitrix24_webhook_{target_entity}" in request.headers.keys():
            bitrix24_url = request.headers["bitrix24_url"]
        else:
            error_message = f"Missing header bitrix24_webhook_{target_entity}"
            logger.error(f"Failed: {error_message}", extra=extra_logs)
            update_submission_status(submission, "failed", error_message)
        bitrix24_client = Bitrix24(bitrix24_url)

        response = bitrix24_client.request(
            "POST",
            bitrix24_url,
            submission,
            params=payload[target_entity],
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
