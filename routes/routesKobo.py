from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
import requests
import base64
import csv
import io
import os
import uuid
import json
from enum import Enum
from utils.utils121 import login121
from utils.utilsKobo import (
    add_submission,
    clean_kobo_data,
    get_attachment_dict,
    get_kobo_attachment,
    update_submission_status,
    required_headers_121_kobo,
    required_headers_linked_kobo,
)
from utils.logger import logger

router = APIRouter()


@router.post("/update-kobo-csv")
async def prepare_kobo_validation(
    request: Request,
    programId: int,
    kobousername: str,
    dependencies=Depends(required_headers_121_kobo),
):
    """
    Prepare Kobo validation by fetching data from 121 platform,
    converting it to CSV, and uploading to Kobo.
    """

    access_token = login121(
        request.headers["url121"],
        request.headers["username121"],
        request.headers["password121"],
    )

    # Fetch data from 121 platform
    response = requests.get(
        f"{request.headers['url121']}/api/programs/{programId}/metrics/export-list/all-people-affected",
        headers={"Cookie": f"access_token_general={access_token}"},
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail="Failed to fetch data from 121 platform",
        )

    data = response.json()

    # Convert JSON to CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Ensure we have data to process
    if data and "data" in data and len(data["data"]) > 0:
        # Get the keys (column names) from the first row
        fieldnames = list(data["data"][0].keys())

        # Write header
        writer.writerow(fieldnames)

        # Write rows
        for row in data["data"]:
            # Create a list of values in the same order as fieldnames
            row_data = [row.get(field, "") for field in fieldnames]
            writer.writerow(row_data)

    csv_content = output.getvalue().encode("utf-8")

    # Prepare the payload for Kobo
    base64_encoded_csv = base64.b64encode(csv_content).decode("utf-8")
    metadata = json.dumps({"filename": "ValidationDataFrom121.csv"})

    payload = {
        "description": "default",
        "file_type": "form_media",
        "metadata": metadata,
        "base64Encoded": f"data:text/csv;base64,{base64_encoded_csv}",
    }

    # Kobo headers
    headers = {
        "Authorization": f"Token {request.headers['kobotoken']}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # If exists, remove existing ValidationDataFrom121.csv
    media_response = requests.get(
        f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}/files/",
        headers=headers,
    )
    if media_response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code, detail="Failed to fetch media from kobo"
        )

    media = media_response.json()

    # Check if ValidationDataFrom121.csv exists and get its uid
    existing_file_uid = None
    for file in media.get("results", []):
        if file.get("metadata", {}).get("filename") == "ValidationDataFrom121.csv":
            existing_file_uid = file.get("uid")
            break

    # If the file exists, delete it
    if existing_file_uid:
        delete_response = requests.delete(
            f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}/files/{existing_file_uid}/",
            headers={"Authorization": f"Token {request.headers['kobotoken']}"},
        )
        if delete_response.status_code != 204:
            raise HTTPException(
                status_code=delete_response.status_code,
                detail="Failed to delete existing file from Kobo",
            )

    upload_response = requests.post(
        f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}/files/",
        headers=headers,
        data=payload,
    )

    if upload_response.status_code != 201:
        raise HTTPException(
            status_code=upload_response.status_code,
            detail="Failed to upload file to Kobo",
        )

    # Redeploy the Kobo form
    redeploy_url = f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}/deployment/"
    redeploy_payload = {"active": True}

    redeploy_response = requests.patch(
        redeploy_url, headers=headers, json=redeploy_payload
    )

    if redeploy_response.status_code != 200:
        raise HTTPException(
            status_code=redeploy_response.status_code,
            detail="Failed to redeploy Kobo form",
        )

    return {
        "message": "Validation data prepared and uploaded successfully",
        "kobo_response": upload_response.json(),
    }


###############


class system(str, Enum):
    system_generic = "generic"
    system_espo = "espocrm"
    system_121 = "121"


@router.post("/create-kobo-headers")
async def create_kobo_headers(
    json_data: dict,
    system: system,
    koboassetId: str,
    kobotoken: str,
    hookId: str = None,
):
    """Utility endpoint to automatically create the necessary headers in Kobo. \n
    Does only support the IFRC server kobo.ifrc.org \n
    ***NB: if you want to duplicate an endpoint, please also use the Hook ID query param***
    """

    if json_data is None:
        raise HTTPException(status_code=400, detail="JSON data is required")

    target_url = f"https://kobo.ifrc.org/api/v2/assets/{koboassetId}/hooks/"
    koboheaders = {"Authorization": f"Token {kobotoken}"}

    if hookId is None:
        payload = {
            "name": "koboconnect",
            "endpoint": f"https://kobo-connect.azurewebsites.net/kobo-to-{system}",
            "active": True,
            "subset_fields": [],
            "email_notification": True,
            "export_type": "json",
            "auth_level": "no_auth",
            "settings": {"custom_headers": {}},
            "payload_template": "",
        }

        payload["settings"]["custom_headers"] = json_data
    else:
        get_url = f"https://kobo.ifrc.org/api/v2/assets/{koboassetId}/hooks/{hookId}"
        hook = requests.get(get_url, headers=koboheaders)
        hook = hook.json()
        hook["name"] = "Duplicate of " + hook["name"]

        def remove_keys(data, keys_to_remove):
            for key in keys_to_remove:
                if key in data:
                    del data[key]
            return data

        keys_to_remove = [
            "url",
            "logs_url",
            "asset",
            "uid",
            "success_count",
            "failed_count",
            "pending_count",
            "date_modified",
        ]
        payload = remove_keys(hook, keys_to_remove)

    response = requests.post(target_url, headers=koboheaders, json=payload)

    if response.status_code == 200 or 201:
        return JSONResponse(content={"message": "Sucess"})
    else:
        return JSONResponse(
            content={"message": "Failed to post data to the target endpoint"},
            status_code=response.status_code,
        )


@router.post("/kobo-to-linked-kobo")
async def kobo_to_linked_kobo(
    request: Request, dependencies=Depends(required_headers_linked_kobo)
):
    """Update a multiple-choice question in a Kobo form (child) based on the submissions of another one (parent)."""

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

    # get submissions of parent form
    target_url = f"https://kobo.ifrc.org/api/v2/assets/{request.headers['parentasset']}/data/?format=json"
    koboheaders = {"Authorization": f"Token {request.headers['kobotoken']}"}
    response = requests.get(target_url, headers=koboheaders)
    parent_submissions = json.loads(response.content)
    print("parent_submissions")
    print(parent_submissions["results"][0])

    # create new choice list based on parent form submissions
    new_choices_form, kuids, names = [], [], []
    for parent_submission in parent_submissions["results"]:
        for key in parent_submission.keys():
            if key.split("/")[-1] == request.headers["parentquestion"]:
                name = parent_submission[key]
                if name in names:
                    continue  # avoid duplicate names
                names.append(name)

                kuid = str(uuid.uuid4())[:10].replace("-", "")
                while kuid in kuids:
                    kuid = str(uuid.uuid4())[:10].replace(
                        "-", ""
                    )  # avoid duplicate kuids
                kuids.append(kuid)

                new_choices_form.append(
                    {
                        "name": name,
                        "$kuid": kuid,
                        "label": [name],
                        "list_name": request.headers["childlist"],
                        "$autovalue": name,
                    }
                )
    print("new_choices_form")
    print(new_choices_form)

    # get child form
    target_url = f"https://kobo.ifrc.org/api/v2/assets/{request.headers['childasset']}/?format=json"
    response = requests.get(target_url, headers=koboheaders)
    assetdata = json.loads(response.content)
    print("child_choices")
    print(assetdata["content"]["choices"])

    # update child form with new choice list
    assetdata["content"]["choices"] = [
        choice
        for choice in assetdata["content"]["choices"]
        if choice["list_name"] != request.headers["childlist"]
    ]
    assetdata["content"]["choices"].extend(new_choices_form)
    logger.info("update child form with new choice list")
    logger.info(assetdata)
    response = requests.patch(target_url, headers=koboheaders, json=assetdata)

    # get latest form version id
    target_url = f"https://kobo.ifrc.org/api/v2/assets/{request.headers['childasset']}/?format=json"
    response = requests.get(target_url, headers=koboheaders)
    newassetdata = json.loads(response.content)
    newversionid = newassetdata["version_id"]

    # deploy latest form version id
    target_url = f"https://kobo.ifrc.org/api/v2/assets/{request.headers['childasset']}/deployment/"
    payload = {"version_id": newversionid, "active": True}
    response = requests.patch(target_url, headers=koboheaders, data=payload)

    if response.status_code == 200:
        logger.info("Success", extra=extra_logs)
        update_submission_status(submission, "success")
        return JSONResponse(status_code=200, content={"detail": "Success"})
    else:
        logger.error("Failed", extra=extra_logs)
        update_submission_status(submission, "failed")
