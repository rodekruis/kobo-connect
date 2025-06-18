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


def required_headers_bitrix24(
    targeturl: str = Header(), koboasset: str = Header(), kobotoken: str = Header()
):
    return targeturl, koboasset, kobotoken


@router.post("/kobo-to-bitrix24", tags=["Bitrix24"])
async def kobo_to_bitrix24(
    request: Request, dependencies=Depends(required_headers_bitrix24)
):
    """Send a Kobo submission to Bitrix24."""

    kobo_data = await request.json()
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
    submission = add_submission(kobo_data)
    if submission["status"] == "success":
        return JSONResponse(
            status_code=200,
            content={"detail": "Submission has already been successfully processed"},
        )

    # get kobo attachments
    kobotoken = request.headers["kobotoken"]
    koboasset = request.headers["koboasset"]
    attachments = get_attachment_dict(kobo_data, kobotoken, koboasset)

    # initialize Bitrix24 API client
    client = Bitrix24(request.headers["targeturl"])

    # create API payload body
    payload, target_entity = {}, ""
    for kobo_field, target_field in request.headers.items():

        multi = False
        repeat, repeat_no, repeat_question = False, 0, ""

        # determine if kobo_field is of type multi or repeat
        if "multi:" in kobo_field:
            kobo_field = kobo_field.split(":")[1]
            multi = True
        if "repeat:" in kobo_field:
            split = kobo_field.split(":")
            kobo_field = split[1]
            repeat_no = int(split[2])
            repeat_question = split[3]
            repeat = True

        # check if kobo_field is in kobo_data
        if kobo_field not in kobo_data.keys():
            continue

        # check if entity is nested in target_field
        if len(target_field.split(":")) == 2:
            target_entity = target_field.split(":")[0]
            target_field = target_field.split(":")[1]
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

        kobo_value_url = str(kobo_value).replace(" ", "_")
        kobo_value_url = re.sub(r"[(,)']", "", kobo_value_url)
        if kobo_value_url not in attachments.keys():
            payload[target_entity][target_field] = kobo_value
        else:
            file_url = attachments[kobo_value_url]["url"]
            file = get_kobo_attachment(file_url, kobotoken)
            file_b64 = base64.b64encode(file).decode("utf8")
            payload[target_entity][
                target_field
            ] = f"data:{attachments[kobo_value_url]['mimetype']};base64,{file_b64}"

    if len(payload) == 0:
        error_message = "No fields found in submission or no entities found in headers"
        logger.error(f"Failed: {error_message}", extra=extra_logs)
        update_submission_status(submission, "failed", error_message)

    for target_entity in payload.keys():

        response = client.request(
            "POST",
            target_entity,
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
