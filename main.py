import uvicorn
from typing import Union
from fastapi import Security, Depends, FastAPI, Request, HTTPException
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
    title="kobo-connect",
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

default_headers = ["accept", "accept-encoding", "content-length", "content-type", "connection", "host", "sentry-trace",
                   "user-agent", "targeturl", "targetapikey", "targetclient", "kobotoken"]


class TargetClient(Enum):
    espo = "EspoCRM"
    one2one = "121"
    none = "none"

def get_kobo_data_id(ID, kobo_token, kobo_asset):
    # Get data from kobo
    headers = {'Authorization': f'Token {kobo_token}'}
    data_request = requests.get(
        f'https://kobonew.ifrc.org/api/v2/assets/{kobo_asset}/data.json/?query={{"_id":{ID}}}',
        headers=headers)
    data = data_request.json()['results'][0]
    return data


def get_kobo_attachment(URL, kobo_token):
    # Get attachment from kobo
    headers = {'Authorization': f'Token {kobo_token}'}
    data_request = requests.get(URL, headers=headers)
    data = data_request.content
    return data


@app.get("/", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url='/docs')


@app.post("/kobo")
async def post_submission(request: Request):
    """post a Kobo submission."""

    for header in ['kobotoken', 'targeturl', 'targetapikey']:
        if header not in request.headers.keys():
            raise HTTPException(
                status_code=400,
                detail=f"{header} needs to be specified in headers"
            )
    kobotoken = request.headers['kobotoken']
    targeturl = request.headers['targeturl']
    targetapikey = request.headers['targetapikey']

    if 'targetclient' in request.headers.keys():
        targetclient = TargetClient(request.headers['targetclient'])
        client = EspoAPI(targeturl, targetapikey)
    else:
        targetclient = TargetClient.none
        client = None

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
    missing_fields = []
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
                file = get_kobo_attachment(file_url, kobotoken)
                file_b64 = base64.b64encode(file).decode("utf8")
                if targetclient == targetclient.espo:
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
                        payload[target_entity][target_field] = f"data:{attachments[kobo_value]['mimetype']};base64,{file_b64}"
                    else:
                        payload[target_field] = f"data:{attachments[kobo_value]['mimetype']};base64,{file_b64}"
        elif kobo_field not in default_headers:
            missing_fields.append(kobo_field)
    if len(missing_fields) > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Kobo field(s) in headers {', '.join(missing_fields)} are missing from submission"
        )
    print(payload)

    # POST to target API
    if is_entity:
        target_response = {}
        for target_entity in payload.keys():
            if targetclient == targetclient.espo:
                response = client.request('POST', target_entity, payload[target_entity])
            else:
                response = requests.post(targeturl, headers={'X-Api-Key': targetapikey}, data=payload[target_entity])
            if response.status_code > 230:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.content
                )
            else:
                target_response[target_entity] = response.content
    else:
        if targetclient == targetclient.espo:
            raise HTTPException(
                status_code=400,
                detail=f"EspoCRM client needs the entity name to be specified in headers as <entity>.<field>"
            )
        else:
            response = requests.post(targeturl, headers={'X-Api-Key': targetapikey}, data=payload)
            print(response, response.content)
            target_response = response.content.decode("utf-8")
    return JSONResponse(status_code=200, content=target_response)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(port), reload=True)