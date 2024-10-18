from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from utils.utilsKobo import (
    add_submission,
    clean_kobo_data,
    get_attachment_dict,
    get_kobo_attachment,
    update_submission_status,
)
from utils.utilsEspo import espo_request, required_headers_espocrm
from utils.logger import logger
from clients.espo_api_client import EspoAPI
import os
import re
import base64

router = APIRouter()


@router.post("/kobo-to-espocrm")
async def kobo_to_espocrm(
    request: Request, dependencies=Depends(required_headers_espocrm)
):
    """Send a Kobo submission to EspoCRM."""

    kobo_data = await request.json()
    extra_logs = {"environment": os.getenv("ENV")}
    try:
        extra_logs["kobo_form_id"] = str(kobo_data["_xform_id_string"])
        extra_logs["kobo_form_version"] = str(kobo_data["__version__"])
        extra_logs["kobo_submission_id"] = str(kobo_data["_id"])
    except KeyError:
        return JSONResponse(
            status_code=422,
            content={"detail": "Not a valid Kobo submission"},
        )
    target_response = {}

    # store the submission uuid and status, to avoid duplicate submissions
    submission = add_submission(kobo_data)
    if submission["status"] == "success":
        logger.info(
            "Submission has already been successfully processed", extra=extra_logs
        )
        return JSONResponse(
            status_code=200,
            content={"detail": "Submission has already been successfully processed"},
        )

    kobo_data = clean_kobo_data(kobo_data)

    # Check if 'skipConnect' is present and set to True in kobo_data
    if "skipconnect" in kobo_data.keys() and kobo_data["skipconnect"] == "1":
        logger.info("Skipping submission", extra=extra_logs)
        return JSONResponse(status_code=200, content={"message": "Skipping submission"})

    kobotoken, koboasset = None, None
    if "kobotoken" in request.headers.keys():
        kobotoken = request.headers["kobotoken"]
    if "koboasset" in request.headers.keys():
        koboasset = request.headers["koboasset"]
    client = EspoAPI(request.headers["targeturl"], request.headers["targetkey"])
    attachments = get_attachment_dict(kobo_data, kobotoken, koboasset)

    # check if records need to be updated
    update_record_payload = {}
    if "updaterecordby" in request.headers.keys():
        if "updaterecordby" in kobo_data.keys():
            if (
                kobo_data["updaterecordby"] != ""
                and kobo_data["updaterecordby"] is not None
            ):
                update_record_entity = request.headers["updaterecordby"].split(".")[0]
                update_record_field = request.headers["updaterecordby"].split(".")[1]
                update_record_payload[update_record_entity] = {
                    "field": update_record_field,
                    "value": kobo_data["updaterecordby"],
                }
            kobo_data.pop("updaterecordby")

    # Create API payload body
    payload, target_entity = {}, ""
    for kobo_field, target_field in request.headers.items():

        kobo_value, multi, repeat, repeat_no, repeat_question = "", False, False, 0, ""

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

        # process individual field; if it's an attachment, upload it to EspoCRM
        kobo_value_url = str(kobo_value).replace(" ", "_")
        kobo_value_url = re.sub(r"[(,)']", "", kobo_value_url)
        if kobo_value_url not in attachments.keys():
            payload[target_entity][target_field] = kobo_value
        else:
            file_url = attachments[kobo_value_url]["url"]
            if not kobotoken:
                error_message = "'kobotoken' needs to be specified in headers to upload attachments to EspoCRM"
                logger.error(f"Failed: {error_message}", extra=extra_logs)
                update_submission_status(submission, "failed", error_message)

            # encode attachment in base64
            file = get_kobo_attachment(file_url, kobotoken)
            file_b64 = base64.b64encode(file).decode("utf8")
            # upload attachment to target
            attachment_payload = {
                "name": kobo_value,
                "type": attachments[kobo_value_url]["mimetype"],
                "role": "Attachment",
                "relatedType": target_entity,
                "field": target_field,
                "file": f"data:{attachments[kobo_value_url]['mimetype']};base64,{file_b64}",
            }
            attachment_record = espo_request(
                submission,
                client,
                "POST",
                "Attachment",
                params=attachment_payload,
                logs=extra_logs,
            )
            # link field to attachment
            payload[target_entity][f"{target_field}Id"] = attachment_record["id"]

    if len(payload) == 0:
        error_message = "No fields found in submission or no entities found in headers"
        logger.error(f"Failed: {error_message}", extra=extra_logs)
        update_submission_status(submission, "failed", error_message)

    for target_entity in payload.keys():

        if target_entity not in update_record_payload.keys():
            # create new record of target entity
            response = espo_request(
                submission,
                client,
                "POST",
                target_entity,
                params=payload[target_entity],
                logs=extra_logs,
            )
        else:
            # find target record
            params = {
                "where": [
                    {
                        "type": "contains",
                        "attribute": update_record_payload[target_entity]["field"],
                        "value": update_record_payload[target_entity]["value"],
                    }
                ]
            }
            records = espo_request(
                submission, client, "GET", target_entity, params=params, logs=extra_logs
            )["list"]
            if len(records) != 1:
                error_message = (
                    f"Found {len(records)} records of entity {target_entity} "
                    f"with field {update_record_payload[target_entity]['field']} "
                    f"equal to {update_record_payload[target_entity]['value']}"
                )
                logger.error(f"Failed: {error_message}", extra=extra_logs)
                update_submission_status(submission, "failed", error_message)
                response = {}
            else:
                # update target record
                response = espo_request(
                    submission,
                    client,
                    "PUT",
                    f"{target_entity}/{records[0]['id']}",
                    params=payload[target_entity],
                    logs=extra_logs,
                )
        if "id" not in response.keys():
            error_message = response.content.decode("utf-8")
            logger.error(f"Failed: {error_message}", extra=extra_logs)
            update_submission_status(submission, "failed", error_message)
        else:
            target_response[target_entity] = response

    logger.info("Success", extra=extra_logs)
    update_submission_status(submission, "success")
    return JSONResponse(status_code=200, content=target_response)
