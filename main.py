import uvicorn
from typing import Union
from fastapi import Security, Depends, FastAPI, APIRouter, Request, HTTPException, Header
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader, APIKey
from pydantic import BaseModel
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

def required_headers(
        targeturl: str = Header(),
        targetkey: str = Header()):
    return targeturl, targetkey


def required_headers_121(
        targeturl: str = Header(),
        targetkey: str = Header(),
        programid: str = Header()):
    return targeturl, targetkey, programid


def get_kobo_attachment(URL, kobo_token):
    # Get attachment from kobo
    headers = {'Authorization': f'Token {kobo_token}'}
    data_request = requests.get(URL, headers=headers)
    data = data_request.content
    return data


@app.get("/", include_in_schema=False)
async def docs_redirect():
    """Redirect base URL to docs."""
    return RedirectResponse(url='/docs')


@app.post("/kobo-to-espocrm")
async def kobo_to_espocrm(request: Request, dependencies=Depends(required_headers)):
    """Send a Kobo submission to EspoCRM."""

    client = EspoAPI(request.headers['targeturl'], request.headers['targetkey'])

    kobo_data = await request.json()
    kobo_data = {k.lower(): v for k, v in kobo_data.items()}

    # remove group names
    for key in list(kobo_data.keys()):
        new_key = key.split('/')[-1]
        kobo_data[new_key] = kobo_data.pop(key)

    # Create a dictionary to map the attachment filenames to their URL
    attachments = {}
    if '_attachments' in kobo_data.keys():
        if kobo_data['_attachments'] is not None:
            if 'kobotoken' not in request.headers.keys():
                raise HTTPException(
                    status_code=400,
                    detail=f"kobotoken needs to be specified in headers to upload attachments to EspoCRM"
                )
            for attachment in kobo_data['_attachments']:
                filename = attachment['filename'].split('/')[-1]
                downloadurl = attachment['download_url']
                mimetype = attachment['mimetype']
                attachments[filename] = {'url': downloadurl, 'mimetype': mimetype}

    # Create API payload body
    payload, target_entity, is_entity = {}, "", False
    for kobo_field, target_field in request.headers.items():
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

            kobo_value = kobo_data[kobo_field].replace(" ", "_")
            if kobo_value not in attachments.keys():
                if is_entity:
                    payload[target_entity][target_field] = kobo_value
                else:
                    payload[target_field] = kobo_value
            else:
                file_url = attachments[kobo_value]['url']
                # encode image in base64
                file = get_kobo_attachment(file_url, request.headers['kobotoken'])
                file_b64 = base64.b64encode(file).decode("utf8")
                # upload attachment to target
                attachment_payload = {
                    "name": kobo_value,
                    "type": attachments[kobo_value]['mimetype'],
                    "role": "Attachment",
                    "relatedType": target_entity,
                    "field": target_field,
                    "file": f"data:{attachments[kobo_value]['mimetype']};base64,{file_b64}"
                }
                attachment_record = client.request('POST', 'Attachment', attachment_payload)
                # link field to attachment
                payload[target_entity][f"{target_field}Id"] = attachment_record['id']
        else:
            if is_entity:
                payload[target_entity][target_field] = ''
            else:
                payload[target_field] = ''
    # POST to target API
    if is_entity:
        target_response = {}
        for target_entity in payload.keys():
            response = client.request('POST', target_entity, payload[target_entity])
            if 'id' not in response.keys():
                raise HTTPException(
                    status_code=500,
                    detail=response.content
                )
            else:
                target_response[target_entity] = response
    else:
        raise HTTPException(
            status_code=400,
            detail=f"EspoCRM client needs the entity name to be specified in headers as <entity>.<field>"
        )
    return JSONResponse(status_code=200, content=target_response)


@app.post("/kobo-to-121")
async def kobo_to_121(request: Request, dependencies=Depends(required_headers_121)):
    """Send a Kobo submission to 121."""

    kobo_data = await request.json()
    kobo_data = {k.lower(): v for k, v in kobo_data.items()}

    # remove group names
    for key in list(kobo_data.keys()):
        new_key = key.split('/')[-1]
        kobo_data[new_key] = kobo_data.pop(key)

    # Create a dictionary to map the attachment filenames to their URL
    attachments = {}
    if '_attachments' in kobo_data.keys():
        if kobo_data['_attachments'] is not None:
            for attachment in kobo_data['_attachments']:
                filename = attachment['filename'].split('/')[-1]
                downloadurl = attachment['download_url']
                mimetype = attachment['mimetype']
                attachments[filename] = {'url': downloadurl, 'mimetype': mimetype}

    # Create API payload body
    payload, target_entity, is_entity = {}, "", False
    for kobo_field, target_field in request.headers.items():
        if kobo_field in kobo_data.keys():

            kobo_value = kobo_data[kobo_field].replace(" ", "_")
            if kobo_value not in attachments.keys():
                payload[target_field] = kobo_value
            else:
                payload[target_field] = attachments[kobo_value]['url']
        else:
            payload[target_field] = ''

    # POST to target API
    response = requests.post(
        f"{request.headers['targeturl']}/api/programs/{request.headers['programid']}/registrations/import",
        headers={'Cookie': f"access_token_general={request.headers['targetkey']}"},
        json=payload
    )
    target_response = response.content.decode("utf-8")
    return JSONResponse(status_code=200, content=target_response)


@app.post("/kobo-to-basic")
async def kobo_to_basic(request: Request, dependencies=Depends(required_headers)):
    """Send a Kobo submission to a basic API.
     API Key is passed as 'x-api-key' in headers."""

    kobo_data = await request.json()
    kobo_data = {k.lower(): v for k, v in kobo_data.items()}

    # remove group names
    for key in list(kobo_data.keys()):
        new_key = key.split('/')[-1]
        kobo_data[new_key] = kobo_data.pop(key)

    # Create a dictionary to map the attachment filenames to their URL
    attachments = {}
    if '_attachments' in kobo_data.keys():
        if kobo_data['_attachments'] is not None:
            for attachment in kobo_data['_attachments']:
                filename = attachment['filename'].split('/')[-1]
                downloadurl = attachment['download_url']
                mimetype = attachment['mimetype']
                attachments[filename] = {'url': downloadurl, 'mimetype': mimetype}

    # Create API payload body
    payload, target_entity, is_entity = {}, "", False
    for kobo_field, target_field in request.headers.items():
        if kobo_field in kobo_data.keys():
            kobo_value = kobo_data[kobo_field].replace(" ", "_")
            if kobo_value not in attachments.keys():
                payload[target_field] = kobo_value
            else:
                payload[target_field] = attachments[kobo_value]['url']
        else:
            payload[target_field] = None

    # POST to target API
    response = requests.post(request.headers['targeturl'], headers={'x-api-key': request.headers['targetkey']},
                             data=payload)
    target_response = response.content.decode("utf-8")
    return JSONResponse(status_code=200, content=target_response)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(port), reload=True)