import uvicorn
from typing import Union
from fastapi import Security, Depends, FastAPI, APIRouter, Request, HTTPException, Header
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader, APIKey
from pydantic import BaseModel
from enum import Enum
from clients.espo_api_client import EspoAPI
import requests
import os
import json
from enum import Enum
import base64
import logging
import sys
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s : %(levelname)s : %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("requests_oauthlib").setLevel(logging.WARNING)
from dotenv import load_dotenv
load_dotenv()

# load environment variables
port = os.environ["PORT"]

# initialize FastAPI
app = FastAPI(
    title="KoboConnect",
    description="Connect Kobo to anything. \n"
                "Built with love by [NLRC 510](https://www.510.global/). "
                "See [the project on GitHub](https://github.com/rodekruis/kobo-connect) "
                "or [contact us](mailto:support@510.global).",
    version="0.0.1",
    license_info={
        "name": "AGPL-3.0 license",
        "url": "https://www.gnu.org/licenses/agpl-3.0.en.html",
    },
)

class system(str, Enum):
    system_generic = "generic"
    system_espo = "espocrm"
    system_121 = "121"

def required_headers(
        targeturl: str = Header(),
        targetkey: str = Header()):
    return targeturl, targetkey


def required_headers_121(
        url121: str = Header(),
        username121: str = Header(),
        password121: str = Header()):
    return url121, username121, password121


def get_kobo_attachment(URL, kobo_token):
    # Get attachment from kobo
    headers = {'Authorization': f'Token {kobo_token}'}
    data_request = requests.get(URL, headers=headers)
    data = data_request.content
    return data


def get_attachment_dict(kobo_data):
    """Create a dictionary that maps the attachment filenames to their URL."""
    attachments = {}
    if '_attachments' in kobo_data.keys():
        if kobo_data['_attachments'] is not None:
            for attachment in kobo_data['_attachments']:
                filename = attachment['filename'].split('/')[-1]
                downloadurl = attachment['download_url']
                mimetype = attachment['mimetype']
                attachments[filename] = {'url': downloadurl, 'mimetype': mimetype}
    return attachments


def clean_kobo_data(kobo_data):
    kobo_data_clean = {k.lower(): v for k, v in kobo_data.items()}
    # remove group names
    for key in list(kobo_data_clean.keys()):
        new_key = key.split('/')[-1]
        kobo_data_clean[new_key] = kobo_data_clean.pop(key)
    return kobo_data_clean


@app.get("/", include_in_schema=False)
async def docs_redirect():
    """Redirect base URL to docs."""
    return RedirectResponse(url='/docs')


@app.post("/kobo-to-espocrm")
async def kobo_to_espocrm(request: Request, dependencies=Depends(required_headers)):
    """Send a Kobo submission to EspoCRM."""

    client = EspoAPI(request.headers['targeturl'], request.headers['targetkey'])

    kobo_data = await request.json()
    kobo_data = clean_kobo_data(kobo_data)
    attachments = get_attachment_dict(kobo_data)
    
    # check if records need to be updated
    update_record, update_record_payload = False, {}
    if 'updaterecordby' in request.headers.keys():
        if 'updaterecordby' in kobo_data.keys():
            if kobo_data['updaterecordby'] != "" and kobo_data['updaterecordby'] is not None:
                update_record = True
                update_record_entity = request.headers['updaterecordby'].split('.')[0]
                update_record_field = request.headers['updaterecordby'].split('.')[1]
                update_record_payload[update_record_entity] = {
                    'field': update_record_field,
                    'value': kobo_data['updaterecordby']
                }
            kobo_data.pop('updaterecordby')

    # Create API payload body
    payload, target_entity, is_entity = {}, "", False
    for kobo_field, target_field in request.headers.items():
        multi = False
        if "multi." in kobo_field:
            kobo_field = kobo_field.split(".")[1]
            multi = True
        if kobo_field in kobo_data.keys():
            # check if entity is nested in target_field
            if len(target_field.split('.')) == 2:
                target_entity = target_field.split('.')[0]
                target_field = target_field.split('.')[1]
                if target_entity not in payload.keys():
                    payload[target_entity] = {}
                    is_entity = True
            else:
                is_entity = False

            if multi:
                kobo_value = kobo_data[kobo_field].split(" ")
            else:
                kobo_value = kobo_data[kobo_field]
            kobo_value_url = kobo_data[kobo_field].replace(" ", "_")
            if kobo_value_url not in attachments.keys():
                if is_entity:
                    payload[target_entity][target_field] = kobo_value
                else:
                    payload[target_field] = kobo_value
            else:
                file_url = attachments[kobo_value_url]['url']
                if 'kobotoken' not in request.headers.keys():
                    raise HTTPException(
                        status_code=400,
                        detail=f"'kobotoken' needs to be specified in headers to upload attachments to EspoCRM"
                    )
                # encode attachment in base64
                file = get_kobo_attachment(file_url, request.headers['kobotoken'])
                file_b64 = base64.b64encode(file).decode("utf8")
                # upload attachment to target
                attachment_payload = {
                    "name": kobo_value,
                    "type": attachments[kobo_value_url]['mimetype'],
                    "role": "Attachment",
                    "relatedType": target_entity,
                    "field": target_field,
                    "file": f"data:{attachments[kobo_value_url]['mimetype']};base64,{file_b64}"
                }
                attachment_record = client.request('POST', 'Attachment', attachment_payload)
                # link field to attachment
                payload[target_entity][f"{target_field}Id"] = attachment_record['id']

    if is_entity:
        target_response = {}
        for target_entity in payload.keys():
            logger.info(payload)
            if not update_record:
                # create new record of target entity
                response = client.request('POST', target_entity, payload[target_entity])
            elif target_entity in update_record_payload.keys():
                # find target record
                params = {"where": [{
                            "type": "contains",
                            "attribute": update_record_payload[target_entity]['field'],
                            "value": update_record_payload[target_entity]['value']
                }]}
                records = client.request('GET', target_entity, params)['list']
                if len(records) != 1:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Found {len(records)} records of entity {target_entity} "
                               f"with field {update_record_payload[target_entity]['field']} "
                               f"equal to {update_record_payload[target_entity]['value']}"
                    )
                else:
                    # update target record
                    response = client.request('PUT', f"{target_entity}/{records[0]['id']}", payload[target_entity])
            if 'id' not in response.keys():
                raise HTTPException(
                    status_code=500,
                    detail=response.content.decode("utf-8")
                )
            else:
                target_response[target_entity] = response
    else:
        raise HTTPException(
            status_code=400,
            detail=f"EspoCRM client needs the entity name to be specified in headers as '<entity>.<field>'"
        )
    return JSONResponse(status_code=200, content=target_response)


@app.post("/kobo-to-121")
async def kobo_to_121(request: Request, dependencies=Depends(required_headers_121)):
    """Send a Kobo submission to 121."""

    kobo_data = await request.json()
    kobo_data = clean_kobo_data(kobo_data)

    # Check if 'skipConnect' is present and set to True in kobo_data
    if 'skipconnect' in kobo_data and kobo_data['skipconnect'] == '1':
        return JSONResponse(status_code=200, content={"message": "Skipping connection to 121"})
    attachments = get_attachment_dict(kobo_data)

    if 'programid' in request.headers.keys():
        programid = request.headers['programid']
    elif 'programid' in kobo_data.keys():
        programid = kobo_data['programid']
    else:
        raise HTTPException(
            status_code=400,
            detail=f"'programid' needs to be specified in headers or submission body"
        )

    if 'referenceId' in request.headers.keys():
        referenceId = request.headers['referenceId']
    else:
        referenceId = kobo_data['_uuid']

    # Create API payload body
    intvalues = ['maxPayments', 'paymentAmountMultiplier','inclusionScore']
    payload = {}
    for kobo_field, target_field in request.headers.items():
        if kobo_field in kobo_data.keys():
            kobo_value = kobo_data[kobo_field].replace(" ", "_")
            if target_field in intvalues:
                payload[target_field] = int(kobo_data[kobo_field])
            elif kobo_value not in attachments.keys():
                payload[target_field] = kobo_data[kobo_field]
            else:
                payload[target_field] = attachments[kobo_value]['url']
        else:
            payload[target_field] = ""

    payload['referenceId'] = referenceId

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

    # POST to target API
    response = requests.post(
        f"{request.headers['url121']}/api/programs/{programid}/registrations/import",
        headers={'Cookie': f"access_token_general={access_token}"},
        json=[payload]
    )
    target_response = response.content.decode("utf-8")
    return JSONResponse(status_code=response.status_code, content=target_response)

@app.post("/create-kobo-headers")
async def create_kobo_headers(json_data: dict, system: system, kobouser: str, kobopassword: str, koboassetId: str):
    """Utility endpoint to automatically create the necessary headers in Kobo.
    Does only support the IFRC server kobonew.ifrc.org"""
    
    if json_data is None:
        raise HTTPException(status_code=400, detail="JSON data is required")
    
    target_url = f"https://kobonew.ifrc.org/api/v2/assets/{koboassetId}/hooks/"
    auth = (kobouser, kobopassword)

    payload = {
        "name": "koboconnect",
        "endpoint": f"https://kobo-connect.azurewebsites.net/kobo-to-{system}",
        "active": True,
        "subset_fields": [],
        "email_notification": True,
        "export_type": "json",
        "auth_level": "no_auth",
        "settings": {
            "custom_headers": {
            }
        },
        "payload_template": ""
    }

    payload["settings"]["custom_headers"] = json_data

    response = requests.post(target_url, auth=auth, json=payload)

    if response.status_code == 200 or 201:
        return JSONResponse(content={"message": "Sucess"})
    else:
        return JSONResponse(content={"message": "Failed to post data to the target endpoint"}, status_code=response.status_code)


@app.post("/kobo-to-generic")
async def kobo_to_generic(request: Request, dependencies=Depends(required_headers)):
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
                file_url = attachments[kobo_value]['url']
                if 'kobotoken' not in request.headers.keys():
                    raise HTTPException(
                        status_code=400,
                        detail=f"'kobotoken' needs to be specified in headers to upload attachments"
                    )
                # encode attachment in base64
                file = get_kobo_attachment(file_url, request.headers['kobotoken'])
                file_b64 = base64.b64encode(file).decode("utf8")
                payload[target_field] = f"data:{attachments[kobo_value]['mimetype']};base64,{file_b64}"

    # POST to target API
    response = requests.post(request.headers['targeturl'], headers={'x-api-key': request.headers['targetkey']},
                             data=payload)
    target_response = response.content.decode("utf-8")
    return JSONResponse(status_code=200, content=target_response)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(port), reload=True)
