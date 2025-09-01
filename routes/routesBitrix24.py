from fastapi import APIRouter, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from utils.cosmos import add_submission, update_submission_status
from utils.utilsKobo import clean_kobo_data, get_attachment_dict, get_kobo_attachment
from utils.logger import logger
from clients.bitrix24_api_client import Bitrix24
import os
import re
import base64
import traceback  # ✅ import traceback for detailed errors

router = APIRouter()

def required_headers_bitrix24(targeturl: str = Header()):
    return targeturl

@router.post("/kobo-to-bitrix24", tags=["Bitrix24"])
async def kobo_to_bitrix24(request: Request, dependencies=Depends(required_headers_bitrix24)):
    """Send a Kobo submission to Bitrix24."""

    try:
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

        submission = add_submission(kobo_data)
        if submission["status"] == "success":
            return JSONResponse(
                status_code=200,
                content={"detail": "Submission has already been successfully processed"},
            )

        try:
            client = Bitrix24(request.headers["targeturl"], request.headers["targetkey"])
        except KeyError:
            raise HTTPException(status_code=400, detail="Missing 'targeturl' or 'targetkey' in headers")

        target_entity = "crm.item.add.json"
        payload = {
            target_entity: {
                "entityTypeId": None,
                "fields": {}
            }
        }

        for kobo_field, target_field in request.headers.items():
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

            if kobo_field not in kobo_data:
                continue

            if len(target_field.split(":")) == 2:
                target_entity_header = target_field.split(":")[0]
                target_field_or_setting = target_field.split(":")[1]
            else:
                continue

            if target_entity_header != target_entity:
                continue

            if target_field_or_setting == "entityTypeId":
                try:
                    payload[target_entity]["entityTypeId"] = int(kobo_data[kobo_field])
                except (ValueError, KeyError):
                    continue
                continue

            if multi:
                kobo_value = kobo_data[kobo_field].split(" ")
            elif repeat:
                if 0 <= repeat_no < len(kobo_data[kobo_field]):
                    kobo_data[kobo_field][repeat_no] = clean_kobo_data(kobo_data[kobo_field][repeat_no])
                    if repeat_question not in kobo_data[kobo_field][repeat_no]:
                        continue
                    kobo_value = kobo_data[kobo_field][repeat_no][repeat_question]
                else:
                    continue
            else:
                kobo_value = kobo_data[kobo_field]

            payload[target_entity]["fields"][target_field_or_setting] = kobo_value

        if (
            target_entity not in payload
            or not payload[target_entity]["fields"]
            or not payload[target_entity]["entityTypeId"]
        ):
            error_message = "No fields or entityTypeId found in submission"
            logger.error(f"Failed: {error_message}", extra=extra_logs)
            update_submission_status(submission, "failed", error_message)
            raise HTTPException(status_code=400, detail=error_message)

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
            raise HTTPException(status_code=500, detail=error_message)

        target_response[target_entity] = response
        logger.info("Success", extra=extra_logs)
        update_submission_status(submission, "success")
        return JSONResponse(status_code=200, content=target_response)

    except Exception as e:
        # ✅ catch and return internal error
        error_detail = f"Unexpected error: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_detail)
        return JSONResponse(status_code=500, content={"detail": error_detail})
