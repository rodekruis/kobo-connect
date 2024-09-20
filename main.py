import uvicorn
import time
from fastapi import (
    Security,
    Depends,
    FastAPI,
    APIRouter,
    Request,
    HTTPException,
    Header,
)
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader, APIKey
from pydantic import BaseModel
import re
from clients.espo_api_client import EspoAPI
import requests
import csv
import pandas as pd
from datetime import datetime
import os
from azure.cosmos.exceptions import CosmosResourceExistsError
import azure.cosmos.cosmos_client as cosmos_client
from enum import Enum
import base64
import sys
import unicodedata
import io
import json
from dotenv import load_dotenv
import logging
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from azure.monitor.opentelemetry.exporter import AzureMonitorLogExporter

# load environment variables
load_dotenv()
port = os.environ["PORT"]

# Set up logs export to Azure Application Insights
logger_provider = LoggerProvider()
set_logger_provider(logger_provider)
exporter = AzureMonitorLogExporter(
    connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

# Attach LoggingHandler to root logger
handler = LoggingHandler()
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.NOTSET)
logger = logging.getLogger(__name__)

# Silence noisy loggers
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("requests_oauthlib").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.ERROR)

# initialize FastAPI
app = FastAPI(
    title="kobo-connect",
    description="Connect Kobo to anything. \n"
    "Built with love by [NLRC 510](https://www.510.global/). "
    "See [the project on GitHub](https://github.com/rodekruis/kobo-connect) "
    "or [contact us](mailto:support@510.global).",
    version="0.0.2",
    license_info={
        "name": "AGPL-3.0 license",
        "url": "https://www.gnu.org/licenses/agpl-3.0.en.html",
    },
)

# initialize CosmosDB
client_ = cosmos_client.CosmosClient(
    os.getenv("COSMOS_URL"),
    {"masterKey": os.getenv("COSMOS_KEY")},
    user_agent="kobo-connect",
    user_agent_overwrite=True,
)
cosmos_db = client_.get_database_client("kobo-connect")
cosmos_container_client = cosmos_db.get_container_client("kobo-submissions")


@app.get("/", include_in_schema=False)
async def docs_redirect():
    """Redirect base URL to docs."""
    return RedirectResponse(url="/docs")


def add_submission(kobo_data):
    """Add submission to CosmosDB. If submission already exists and status is pending, raise HTTPException."""
    submission = {
        "id": str(kobo_data["_uuid"]),
        "uuid": str(kobo_data["formhub/uuid"]),
        "status": "pending",
    }
    try:
        submission = cosmos_container_client.create_item(body=submission)
    except CosmosResourceExistsError:
        submission = cosmos_container_client.read_item(
            item=str(kobo_data["_uuid"]),
            partition_key=str(kobo_data["formhub/uuid"]),
        )
        if submission["status"] == "pending":
            raise HTTPException(
                status_code=400, detail=f"Submission is still being processed."
            )
    return submission


def update_submission_status(submission, status, error_message=None):
    """Update submission status in CosmosDB. If error_message is not none, raise HTTPException."""
    submission["status"] = status
    submission["error_message"] = error_message
    cosmos_container_client.replace_item(item=str(submission["id"]), body=submission)
    if status == "failed":
        raise HTTPException(status_code=400, detail=error_message)


def get_kobo_attachment(URL, kobo_token):
    """Get attachment from kobo"""
    headers = {"Authorization": f"Token {kobo_token}"}
    timeout = time.time() + 60  # 1 minute from now
    while True:
        data_request = requests.get(URL, headers=headers)
        data = data_request.content
        if sys.getsizeof(data) > 1000 or time.time() > timeout:
            break
        time.sleep(10)
    return data


def get_attachment_dict(kobo_data, kobotoken=None, koboasset=None):
    """Create a dictionary that maps the attachment filenames to their URL."""
    attachments, attachments_list = {}, []
    if kobotoken and koboasset and "_id" in kobo_data.keys():
        time.sleep(30)
        headers = {"Authorization": f"Token {kobotoken}"}
        URL = f"https://kobo.ifrc.org/api/v2/assets/{koboasset}/data/{kobo_data['_id']}/?format=json"
        data_request = requests.get(URL, headers=headers)
        data = data_request.json()
        if "_attachments" in data.keys():
            attachments_list = data["_attachments"]
    if len(attachments_list) == 0:
        if "_attachments" in kobo_data.keys():
            attachments_list = kobo_data["_attachments"]
        for attachment in attachments_list:
            filename = attachment["filename"].split("/")[-1]
            downloadurl = attachment["download_large_url"]
            mimetype = attachment["mimetype"]
            attachments[filename] = {"url": downloadurl, "mimetype": mimetype}
    else:
        for attachment in attachments_list:
            filename = attachment["filename"].split("/")[-1]
            downloadurl = (
                "https://kc.ifrc.org/media/original?media_file="
                + attachment["filename"]
            )
            mimetype = attachment["mimetype"]
            attachments[filename] = {"url": downloadurl, "mimetype": mimetype}
    return attachments


def clean_kobo_data(kobo_data):
    """Clean Kobo data by removing group names and converting keys to lowercase."""
    kobo_data_clean = {k.lower(): v for k, v in kobo_data.items()}
    # remove group names
    for key in list(kobo_data_clean.keys()):
        new_key = key.split("/")[-1]
        kobo_data_clean[new_key] = kobo_data_clean.pop(key)
    return kobo_data_clean


def espo_request(submission, espo_client, method, entity, params=None, logs=None):
    """Make a request to EspoCRM. If the request fails, update submission status in CosmosDB."""
    try:
        response = espo_client.request(method, entity, params)
        return response
    except HTTPException as e:
        detail = e.detail if "Unknown Error" not in e.detail else ""
        logger.error(f"Failed: EspoCRM returned {e.status_code} {detail}", extra=logs)
        update_submission_status(submission, "failed", e.detail)


def required_headers_espocrm(targeturl: str = Header(), targetkey: str = Header()):
    return targeturl, targetkey


@app.post("/kobo-to-espocrm")
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


########################################################################################################################


def clean_text(text):
    # Normalize text to remove accents
    normalized_text = unicodedata.normalize("NFD", text)
    # Remove accents and convert to lowercase
    cleaned_text = "".join(
        c for c in normalized_text if not unicodedata.combining(c)
    ).lower()
    return cleaned_text


def required_headers_121(
    url121: str = Header(), username121: str = Header(), password121: str = Header()
):
    return url121, username121, password121


@app.post("/kobo-to-121")
async def kobo_to_121(request: Request, dependencies=Depends(required_headers_121)):
    """Send a Kobo submission to 121."""

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
    extra_logs["121_url"] = request.headers["url121"]

    kobo_data = clean_kobo_data(kobo_data)

    # Check if 'skipConnect' is present and set to True in kobo_data
    if "skipconnect" in kobo_data.keys() and kobo_data["skipconnect"] == "1":
        logger.info("Skipping connection to 121", extra=extra_logs)
        return JSONResponse(
            status_code=200, content={"message": "Skipping connection to 121"}
        )
    kobotoken, koboasset = None, None
    if "kobotoken" in request.headers.keys():
        kobotoken = request.headers["kobotoken"]
    if "koboasset" in request.headers.keys():
        koboasset = request.headers["koboasset"]
    attachments = get_attachment_dict(kobo_data, kobotoken, koboasset)

    if "programid" in request.headers.keys():
        programid = request.headers["programid"]
    elif "programid" in kobo_data.keys():
        programid = kobo_data["programid"]
    else:
        error_message = (
            "'programid' needs to be specified in headers or submission body"
        )
        logger.info(f"Failed: {error_message}", extra=extra_logs)
        raise HTTPException(status_code=400, detail=error_message)
    extra_logs["121_program_id"] = request.headers["programid"]

    if "referenceId" in request.headers.keys():
        referenceId = request.headers["referenceId"]
    else:
        referenceId = kobo_data["_uuid"]

    # Create API payload body
    intvalues = ["maxPayments", "paymentAmountMultiplier", "inclusionScore"]
    payload = {}
    for kobo_field, target_field in request.headers.items():
        if kobo_field in kobo_data.keys():
            kobo_value_url = kobo_data[kobo_field].replace(" ", "_")
            kobo_value_url = re.sub(r"[(,),']", "", kobo_value_url)
            if target_field in intvalues:
                payload[target_field] = int(kobo_data[kobo_field])
            elif target_field == "scope":
                payload[target_field] = clean_text(kobo_data[kobo_field])
            elif kobo_value_url not in attachments.keys():
                payload[target_field] = kobo_data[kobo_field]
            else:
                payload[target_field] = attachments[kobo_value_url]["url"]
        else:
            payload[target_field] = ""

    payload["referenceId"] = referenceId

    # get access token from cookie
    body = {
        "username": request.headers["username121"],
        "password": request.headers["password121"],
    }
    url = f"{request.headers['url121']}/api/users/login"
    login_response = requests.post(url, data=body)
    if login_response.status_code >= 400:
        error_message = login_response.content.decode("utf-8")
        logger.info(
            f"Failed: 121 login returned {login_response.status_code} {error_message}",
            extra=extra_logs,
        )
        raise HTTPException(
            status_code=login_response.status_code, detail=error_message
        )
    access_token = login_response.json()["access_token_general"]

    # POST to 121 import endpoint
    import_response = requests.post(
        f"{request.headers['url121']}/api/programs/{programid}/registrations/import",
        headers={"Cookie": f"access_token_general={access_token}"},
        json=[payload],
    )
    import_response_message = import_response.content.decode("utf-8")
    if 200 <= import_response.status_code <= 299:
        logger.info(
            f"Success: 121 import returned {import_response.status_code} {import_response_message}",
            extra=extra_logs,
        )
    elif import_response.status_code >= 400:
        logger.error(
            f"Failed: 121 import returned {import_response.status_code} {import_response_message}",
            extra=extra_logs,
        )
        raise HTTPException(
            status_code=import_response.status_code, detail=import_response_message
        )
    else:
        logger.warning(
            f"121 import returned {import_response.status_code} {import_response_message}",
            extra=extra_logs,
        )

    return JSONResponse(
        status_code=import_response.status_code, content=import_response_message
    )

########################################################################################################################

@app.post("/kobo-update-121")
async def kobo_update_121(request: Request, dependencies=Depends(required_headers_121)):
    """Update a 121 record from a Kobo submission"""

    kobo_data = await request.json()
    kobo_data = clean_kobo_data(kobo_data)

    kobotoken, koboasset = None, None
    if 'kobotoken' in request.headers.keys():
        kobotoken = request.headers['kobotoken']
    if 'koboasset' in request.headers.keys():
        koboasset = request.headers['koboasset']
    attachments = get_attachment_dict(kobo_data, kobotoken, koboasset)

    if 'programid' in request.headers.keys():
        programid = request.headers['programid']
    elif 'programid' in kobo_data.keys():
        programid = kobo_data['programid']
    else:
        raise HTTPException(
            status_code=400,
            detail=f"'programid' needs to be specified in headers or submission body"
        )

    referenceId = kobo_data['referenceid']
    print(referenceId)
    # get access token from cookie
    body = {'username': request.headers['username121'], 'password': request.headers['password121']}
    url = f"{request.headers['url121']}/api/users/login"
    login = requests.post(url, data=body)
    if login.status_code >= 400:
        raise HTTPException(
            status_code=login.status_code,
            detail=login.content.decode("utf-8")
        )
    access_token = login.json()['access_token_general']

    # Create API payload body
    intvalues = ['maxPayments', 'paymentAmountMultiplier', 'inclusionScore']

    for kobo_field, target_field in request.headers.items():
        payload = {
            "data": {},
            "reason": "Validated during field validation"
        }
        if kobo_field in kobo_data.keys():
            kobo_value_url = kobo_data[kobo_field].replace(" ", "_")
            kobo_value_url = re.sub(r"[(,),']", "", kobo_value_url)
            if target_field in intvalues:
                payload["data"][target_field] = int(kobo_data[kobo_field])
            elif target_field == 'scope':
                payload["data"][target_field] = clean_text(kobo_data[kobo_field])
            elif kobo_value_url not in attachments.keys():
                payload["data"][target_field] = kobo_data[kobo_field]
            else:
                payload["data"][target_field] = attachments[kobo_value_url]['url']

            # POST to target API
            if target_field != 'referenceId':
                response = requests.patch(
                    f"{request.headers['url121']}/api/programs/{programid}/registrations/{referenceId}",
                    headers={'Cookie': f"access_token_general={access_token}"},
                    json=payload
                )

                target_response = response.content.decode("utf-8")
                logger.info(target_response)
        
    status_response = requests.patch(
                    f"{request.headers['url121']}/api/programs/{programid}/registrations/status?dryRun=false&filter.referenceId=$in:{referenceId}",
                    headers={'Cookie': f"access_token_general={access_token}"},
                    json={"status": "validated"}
                )
    
    if status_response.status_code != 202:
        raise HTTPException(status_code=response.status_code, detail="Failed to set status of PA to validated")
                

    return JSONResponse(status_code=response.status_code, content=target_response)

########################################################################################################################

def required_headers_121_kobo(
    url121: str = Header(), username121: str = Header(), password121: str = Header(), kobotoken: str = Header(), koboasset: str = Header()
):
    return url121, username121, password121, kobotoken, koboasset

@app.post("/update-kobo-csv")
async def prepare_kobo_validation(request: Request, programId: int, kobousername: str, dependencies=Depends(required_headers_121_kobo)):
    """
    Prepare Kobo validation by fetching data from 121 platform,
    converting it to CSV, and uploading to Kobo.
    """
    # get access token from cookie
    body = {'username': request.headers['username121'], 'password': request.headers['password121']}
    url = f"{request.headers['url121']}/api/users/login"
    login = requests.post(url, data=body)
    if login.status_code >= 400:
        raise HTTPException(
            status_code=login.status_code,
            detail=login.content.decode("utf-8")
        )
    access_token = login.json()['access_token_general']
    
    # Fetch data from 121 platform
    response = requests.get(
        f"{request.headers['url121']}/api/programs/{programId}/metrics/export-list/all-people-affected", 
        headers={'Cookie': f"access_token_general={access_token}"}
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch data from 121 platform")
    
    data = response.json()

    # Convert JSON to CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Ensure we have data to process
    if data and 'data' in data and len(data['data']) > 0:
        # Get the keys (column names) from the first row
        fieldnames = list(data['data'][0].keys())

        # Write header
        writer.writerow(fieldnames)

        # Write rows
        for row in data['data']:
            # Create a list of values in the same order as fieldnames
            row_data = [row.get(field, '') for field in fieldnames]
            writer.writerow(row_data)

    csv_content = output.getvalue().encode('utf-8')

    # Prepare the payload for Kobo
    base64_encoded_csv = base64.b64encode(csv_content).decode('utf-8')
    metadata = json.dumps({"filename": "ValidationDataFrom121.csv"})
    
    payload = {
        "description": "default",
        "file_type": "form_media",
        "metadata": metadata,
        "base64Encoded": f"data:text/csv;base64,{base64_encoded_csv}"
    }

    # Kobo headers
    headers = {
        "Authorization": f"Token {request.headers['kobotoken']}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    #If exists, remove existing ValidationDataFrom121.csv
    media_response = requests.get(
        f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}/files/",
        headers=headers
        )
    if media_response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch media from kobo")
    
    media = media_response.json()

    # Check if ValidationDataFrom121.csv exists and get its uid
    existing_file_uid = None
    for file in media.get('results', []):
        if file.get('metadata', {}).get('filename') == "ValidationDataFrom121.csv":
            existing_file_uid = file.get('uid')
            break

    # If the file exists, delete it
    if existing_file_uid:
        delete_response = requests.delete(
            f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}/files/{existing_file_uid}/",
            headers={"Authorization": f"Token {request.headers['kobotoken']}"}
        )
        if delete_response.status_code != 204:
            raise HTTPException(status_code=delete_response.status_code, detail="Failed to delete existing file from Kobo")

    
    upload_response = requests.post(
        f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}/files/",
        headers=headers,
        data=payload
    )

    if upload_response.status_code != 201:
        raise HTTPException(status_code=upload_response.status_code, detail="Failed to upload file to Kobo")

    # Redeploy the Kobo form
    redeploy_url = f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}/deployment/"
    redeploy_payload = {"active": True}
    
    redeploy_response = requests.patch(
        redeploy_url,
        headers=headers,
        json=redeploy_payload
    )

    if redeploy_response.status_code != 200:
        raise HTTPException(status_code=redeploy_response.status_code, detail="Failed to redeploy Kobo form")


    return {"message": "Validation data prepared and uploaded successfully", "kobo_response": upload_response.json()}


########################################################################################################################


class system(str, Enum):
    system_generic = "generic"
    system_espo = "espocrm"
    system_121 = "121"


@app.post("/create-kobo-headers")
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


########################################################################################################################


def required_headers_kobo(kobotoken: str = Header(), koboasset: str = Header()):
    return kobotoken, koboasset


@app.get("/121-program")
async def create_121_program_from_kobo(
    request: Request, dependencies=Depends(required_headers_kobo)
):
    """Utility endpoint to automatically create a 121 Program in 121 from a koboform, including REST Service \n
    Does only support the IFRC server kobo.ifrc.org \n
    ***NB: if you want to duplicate an endpoint, please also use the Hook ID query param***
    """

    koboUrl = f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}"
    koboheaders = {"Authorization": f"Token {request.headers['kobotoken']}"}
    data_request = requests.get(f"{koboUrl}/?format=json", headers=koboheaders)
    if data_request.status_code >= 400:
        raise HTTPException(
            status_code=data_request.status_code,
            detail=data_request.content.decode("utf-8"),
        )
    data = data_request.json()

    survey = pd.DataFrame(data["content"]["survey"])
    choices = pd.DataFrame(data["content"]["choices"])

    type_mapping = {}
    with open("mappings/kobo121fieldtypes.csv", newline="") as csvfile:
        reader = csv.reader(csvfile, delimiter="\t")
        for row in reader:
            if len(row) == 2:
                type_mapping[row[0]] = row[1]

    mappingdf = pd.read_csv("mappings/kobo121fieldtypes.csv", delimiter="\t")

    CHECKFIELDS = [
        "validation",
        "phase",
        "location",
        "ngo",
        "language",
        "titlePortal",
        "description",
        "startDate",
        "endDate",
        "currency",
        "distributionFrequency",
        "distributionDuration",
        "fixedTransferValue",
        "financialServiceProviders",
        "targetNrRegistrations",
        "tryWhatsAppFirst",
        "phoneNumberPlaceholder",
        "aboutProgram",
        "fullnameNamingConvention",
        "enableMaxPayments",
        "phoneNumber",
        "preferredLanguage",
        "budget",
        "maxPayments",
        "fspName",
    ]

    # First check if all setup fields are in the xlsform
    FIELDNAMES = survey["name"].to_list()
    MISSINGFIELDS = []
    for checkfield in CHECKFIELDS:
        if checkfield not in FIELDNAMES:
            MISSINGFIELDS.append(checkfield)

    if len(MISSINGFIELDS) != 0:
        print("Missing hidden fields in the template: ", MISSINGFIELDS)

    lookupdict = dict(zip(survey["name"], survey["default"]))
    fspquestions = []

    if "tags" in survey.columns:
        dedupedict = dict(zip(survey["name"], survey["tags"]))

        for key, value in dedupedict.items():
            if isinstance(value, list) and any("fsp" in item for item in value):
                fspquestions.append(key)
            elif isinstance(value, list) and any("dedupe" in item for item in value):
                dedupedict[key] = True
            else:
                dedupedict[key] = False

    else:
        survey["tags"] = False
        dedupedict = dict(zip(survey["name"], survey["tags"]))

    # Create the JSON structure
    data = {
        "published": True,
        "validation": lookupdict["validation"].upper() == "TRUE",
        "phase": lookupdict["phase"],
        "location": lookupdict["location"],
        "ngo": lookupdict["ngo"],
        "titlePortal": {lookupdict["language"]: lookupdict["titlePortal"]},
        "titlePaApp": {lookupdict["language"]: lookupdict["titlePortal"]},
        "description": {"en": ""},
        "startDate": datetime.strptime(lookupdict["startDate"], "%d/%m/%Y").isoformat(),
        "endDate": datetime.strptime(lookupdict["endDate"], "%d/%m/%Y").isoformat(),
        "currency": lookupdict["currency"],
        "distributionFrequency": lookupdict["distributionFrequency"],
        "distributionDuration": int(lookupdict["distributionDuration"]),
        "fixedTransferValue": int(lookupdict["fixedTransferValue"]),
        "paymentAmountMultiplierFormula": "",
        "financialServiceProviders": [{"fsp": lookupdict["financialServiceProviders"]}],
        "targetNrRegistrations": int(lookupdict["targetNrRegistrations"]),
        "tryWhatsAppFirst": lookupdict["tryWhatsAppFirst"].upper() == "TRUE",
        "phoneNumberPlaceholder": lookupdict["phoneNumberPlaceholder"],
        "programCustomAttributes": [],
        "programQuestions": [],
        "aboutProgram": {lookupdict["language"]: lookupdict["aboutProgram"]},
        "fullnameNamingConvention": [lookupdict["fullnameNamingConvention"]],
        "languages": [lookupdict["language"]],
        "enableMaxPayments": lookupdict["enableMaxPayments"].upper() == "TRUE",
        "allowEmptyPhoneNumber": False,
        "enableScope": False,
    }

    koboConnectHeader = ["fspName", "preferredLanguage", "maxPayments"]

    for index, row in survey.iterrows():
        if (
            row["type"].split()[0] in mappingdf["kobotype"].tolist()
            and row["name"] not in CHECKFIELDS
            and row["name"] not in fspquestions
        ):
            koboConnectHeader.append(row["name"])
            question = {
                "name": row["name"],
                "label": {"en": str(row["label"][0])},
                "answerType": type_mapping[row["type"].split()[0]],
                "questionType": "standard",
                "options": [],
                "scoring": {},
                "persistence": True,
                "pattern": "",
                "phases": [],
                "editableInPortal": True,
                "export": ["all-people-affected", "included"],
                "shortLabel": {
                    "en": row["name"],
                },
                "duplicateCheck": dedupedict[row["name"]],
                "placeholder": "",
            }
            if type_mapping[row["type"].split()[0]] == "dropdown":
                filtered_df = choices[
                    choices["list_name"] == row["select_from_list_name"]
                ]
                for index, row in filtered_df.iterrows():
                    option = {
                        "option": row["name"],
                        "label": {"en": str(row["label"][0])},
                    }
                    question["options"].append(option)
            data["programQuestions"].append(question)
        if row["name"] == "phoneNumber":
            koboConnectHeader.append("phoneNumber")
            question = {
                "name": "phoneNumber",
                "label": {"en": "Phone Number"},
                "answerType": "tel",
                "questionType": "standard",
                "options": [],
                "scoring": {},
                "persistence": True,
                "pattern": "",
                "phases": [],
                "editableInPortal": True,
                "export": ["all-people-affected", "included"],
                "shortLabel": {
                    "en": row["name"],
                },
                "duplicateCheck": dedupedict[row["name"]],
                "placeholder": "",
            }
            data["programQuestions"].append(question)

    # Create kobo-connect rest service
    restServicePayload = {
        "name": "Kobo Connect",
        "endpoint": "https://kobo-connect.azurewebsites.net/kobo-to-121",
        "active": True,
        "email_notification": True,
        "export_type": "json",
        "settings": {"custom_headers": {}},
    }
    koboConnectHeader = koboConnectHeader + fspquestions
    customHeaders = dict(zip(koboConnectHeader, koboConnectHeader))
    restServicePayload["settings"]["custom_headers"] = customHeaders

    kobo_response = requests.post(
        f"{koboUrl}/hooks/", headers=koboheaders, json=restServicePayload
    )

    if kobo_response.status_code == 200 or 201:
        return JSONResponse(content=data)
    else:
        return JSONResponse(
            content={"message": "Failed"}, status_code=kobo_response.status_code
        )


########################################################################################################################


@app.post("/kobo-to-generic")
async def kobo_to_generic(request: Request):
    """Send a Kobo submission to a generic API.
    API Key is passed as 'x-api-key' in headers."""

    kobo_data = await request.json()
    kobo_data = clean_kobo_data(kobo_data)
    attachments = get_attachment_dict(kobo_data)

    # Create API payload body
    payload = {}
    for kobo_field, target_field in request.headers.items():
        if kobo_field in kobo_data.keys():
            kobo_value = kobo_data[kobo_field].replace(" ", "_")
            if kobo_value not in attachments.keys():
                payload[target_field] = kobo_value
            else:
                file_url = attachments[kobo_value]["url"]
                if "kobotoken" not in request.headers.keys():
                    raise HTTPException(
                        status_code=400,
                        detail=f"'kobotoken' needs to be specified in headers to upload attachments",
                    )
                # encode attachment in base64
                file = get_kobo_attachment(file_url, request.headers["kobotoken"])
                file_b64 = base64.b64encode(file).decode("utf8")
                payload[target_field] = (
                    f"data:{attachments[kobo_value]['mimetype']};base64,{file_b64}"
                )

    # POST to target API
    response = requests.post(
        request.headers["targeturl"],
        headers={"x-api-key": request.headers["targetkey"]},
        data=payload,
    )
    target_response = response.content.decode("utf-8")

    return JSONResponse(status_code=200, content=target_response)


@app.get("/health")
async def health():
    """Get health of instance."""
    kobo = requests.get(f"https://kobo.ifrc.org/api/v2")
    return JSONResponse(
        status_code=200,
        content={"kobo-connect": 200, "kobo.ifrc.org": kobo.status_code},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(port), reload=True)
