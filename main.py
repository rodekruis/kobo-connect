import uvicorn
from typing import Union
from fastapi import Security, Depends, FastAPI, APIRouter, Request, HTTPException, Header
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader, APIKey
from pydantic import BaseModel
from enum import Enum
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
import logging
import sys
import unicodedata
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
    version="0.0.2",
    license_info={
        "name": "AGPL-3.0 license",
        "url": "https://www.gnu.org/licenses/agpl-3.0.en.html",
    },
)

# initialize CosmosDB
client_ = cosmos_client.CosmosClient(
    os.getenv('COSMOS_URL'),
    {'masterKey': os.getenv('COSMOS_KEY')},
    user_agent="kobo-connect",
    user_agent_overwrite=True
)
cosmos_db = client_.get_database_client('kobo-connect')
cosmos_container_client = cosmos_db.get_container_client('kobo-submissions')


@app.get("/", include_in_schema=False)
async def docs_redirect():
    """Redirect base URL to docs."""
    return RedirectResponse(url='/docs')


def add_submission(kobo_data):
    """Add submission to CosmosDB. If submission already exists and status is pending, raise HTTPException."""
    submission = {
        'id': str(kobo_data['_uuid']),
        'uuid': str(kobo_data['formhub/uuid']),
        'status': 'pending'
    }
    try:
        submission = cosmos_container_client.create_item(body=submission)
    except CosmosResourceExistsError:
        submission = cosmos_container_client.read_item(
            item=str(kobo_data['_uuid']),
            partition_key=str(kobo_data['formhub/uuid']),
        )
        if submission['status'] == 'pending':
            raise HTTPException(
                status_code=400,
                detail=f"Submission is still being processed."
            )
    return submission


def update_submission_status(submission, status, error_message=None):
    """Update submission status in CosmosDB. If error_message is not none, raise HTTPException."""
    submission['status'] = status
    submission['error_message'] = error_message
    cosmos_container_client.replace_item(
        item=str(submission['id']),
        body=submission
    )
    if status == 'failed':
        raise HTTPException(
            status_code=400,
            detail=error_message
        )


def get_kobo_attachment(URL, kobo_token):
    """Get attachment from kobo"""
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
    """Clean Kobo data by removing group names and converting keys to lowercase."""
    kobo_data_clean = {k.lower(): v for k, v in kobo_data.items()}
    # remove group names
    for key in list(kobo_data_clean.keys()):
        new_key = key.split('/')[-1]
        kobo_data_clean[new_key] = kobo_data_clean.pop(key)
    return kobo_data_clean


def espo_request(submission, espo_client, method, action, params=None):
    """Make a request to EspoCRM. If the request fails, update submission status in CosmosDB."""
    try:
        response = espo_client.request(method, action, params)
        return response
    except HTTPException as e:
        update_submission_status(submission, 'failed', e.detail)


def required_headers_espocrm(
        targeturl: str = Header(),
        targetkey: str = Header()):
    return targeturl, targetkey


@app.post("/kobo-to-espocrm")
async def kobo_to_espocrm(request: Request, dependencies=Depends(required_headers_espocrm)):
    """Send a Kobo submission to EspoCRM."""

    kobo_data = await request.json()
    target_response = {}

    # store the submission uuid and status, to avoid duplicate submissions
    submission = add_submission(kobo_data)
    if submission['status'] == 'success':
        return JSONResponse(
            status_code=200,
            content={"detail": "Submission has already been successfully processed."}
        )
    
    kobo_data = clean_kobo_data(kobo_data)
    client = EspoAPI(request.headers['targeturl'], request.headers['targetkey'])
    attachments = get_attachment_dict(kobo_data)

    # check if records need to be updated
    update_record_payload = {}
    if 'updaterecordby' in request.headers.keys():
        if 'updaterecordby' in kobo_data.keys():
            if kobo_data['updaterecordby'] != "" and kobo_data['updaterecordby'] is not None:
                update_record_entity = request.headers['updaterecordby'].split('.')[0]
                update_record_field = request.headers['updaterecordby'].split('.')[1]
                update_record_payload[update_record_entity] = {
                    'field': update_record_field,
                    'value': kobo_data['updaterecordby']
                }
            kobo_data.pop('updaterecordby')

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
            
        # check if kobo_field is in submission
        if kobo_field not in kobo_data.keys():
            continue
            
        # check if entity is nested in target_field
        if len(target_field.split('.')) == 2:
            target_entity = target_field.split('.')[0]
            target_field = target_field.split('.')[1]
            if target_entity not in payload.keys():
                payload[target_entity] = {}
        else:
            continue

        # get kobo_value based on kobo_field type
        if multi:
            kobo_value = kobo_data[kobo_field].split(" ")
        elif repeat:
            if 0 <= repeat_no < len(kobo_data[kobo_field]):
                kobo_data[kobo_field][repeat_no] = clean_kobo_data(kobo_data[kobo_field][repeat_no])
                if repeat_question not in kobo_data[kobo_field][repeat_no].keys():
                    continue
                kobo_value = kobo_data[kobo_field][repeat_no][repeat_question]
            else:
                continue
        else:
            kobo_value = kobo_data[kobo_field]
            
        # process individual field; if it's an attachment, upload it to EspoCRM
        kobo_value_url = str(kobo_value).replace(" ", "_")
        if kobo_value_url not in attachments.keys():
            payload[target_entity][target_field] = kobo_value
        else:
            file_url = attachments[kobo_value_url]['url']
            if 'kobotoken' not in request.headers.keys():
                update_submission_status(submission, 'failed',
                                         f"'kobotoken' needs to be specified in headers"
                                         f" to upload attachments to EspoCRM")
                
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
            attachment_record = espo_request(submission, client, 'POST', 'Attachment', attachment_payload)
            # link field to attachment
            payload[target_entity][f"{target_field}Id"] = attachment_record['id']

    if len(payload) == 0:
        update_submission_status(submission, 'failed',
                                 f"No fields found in Kobo submission or"
                                 f" no entities found in headers")
        
    for target_entity in payload.keys():
        logger.info(payload)
        if target_entity not in update_record_payload.keys():
            # create new record of target entity
            response = espo_request(submission, client, 'POST', target_entity, payload[target_entity])
        else:
            # find target record
            params = {"where": [{
                        "type": "contains",
                        "attribute": update_record_payload[target_entity]['field'],
                        "value": update_record_payload[target_entity]['value']
            }]}
            records = espo_request(submission, client, 'GET', target_entity, params)['list']
            if len(records) != 1:
                update_submission_status(submission, 'failed',
                                         f"Found {len(records)} records of entity {target_entity} "
                                         f"with field {update_record_payload[target_entity]['field']} "
                                         f"equal to {update_record_payload[target_entity]['value']}")
            else:
                # update target record
                response = espo_request(submission, client, 'PUT', f"{target_entity}/{records[0]['id']}", payload[target_entity])
        if 'id' not in response.keys():
            update_submission_status(submission, 'failed', response.content.decode("utf-8"))
        else:
            target_response[target_entity] = response
    
    update_submission_status(submission, 'success')
    return JSONResponse(status_code=200, content=target_response)

########################################################################################################################


def clean_text(text):
    # Normalize text to remove accents
    normalized_text = unicodedata.normalize('NFD', text)
    # Remove accents and convert to lowercase
    cleaned_text = ''.join(c for c in normalized_text if not unicodedata.combining(c)).lower()
    return cleaned_text


def required_headers_121(
        url121: str = Header(),
        username121: str = Header(),
        password121: str = Header()):
    return url121, username121, password121


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
            elif target_field == 'scope':
                payload[target_field] = clean_text(kobo_data[kobo_field])
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

    if "debug" in request.headers.items():
        logger.info(payload)
    
    logger.info(target_response)

    return JSONResponse(status_code=response.status_code, content=target_response)

########################################################################################################################


class system(str, Enum):
    system_generic = "generic"
    system_espo = "espocrm"
    system_121 = "121"
    
    
@app.post("/create-kobo-headers")
async def create_kobo_headers(json_data: dict, system: system, kobouser: str, kobopassword: str, koboassetId: str, hookId: str = None):
    """Utility endpoint to automatically create the necessary headers in Kobo. \n
    Does only support the IFRC server kobo.ifrc.org \n
    ***NB: if you want to duplicate an endpoint, please also use the Hook ID query param***"""
    
    if json_data is None:
        raise HTTPException(status_code=400, detail="JSON data is required")
    
    target_url = f"https://kobo.ifrc.org/api/v2/assets/{koboassetId}/hooks/"
    auth = (kobouser, kobopassword)

    if hookId is None:
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
    else:
        get_url = f"https://kobo.ifrc.org/api/v2/assets/{koboassetId}/hooks/{hookId}"
        hook = requests.get(get_url, auth=auth)
        hook = hook.json()
        hook["name"]="Duplicate of " + hook["name"]
        def remove_keys(data, keys_to_remove):
            for key in keys_to_remove:
                if key in data:
                    del data[key]
            return data
        
        keys_to_remove = ["url","logs_url", "asset", "uid", "success_count","failed_count","pending_count","date_modified"]
        payload = remove_keys(hook,keys_to_remove)

    response = requests.post(target_url, auth=auth, json=payload)

    if response.status_code == 200 or 201:
        return JSONResponse(content={"message": "Sucess"})
    else:
        return JSONResponse(content={"message": "Failed to post data to the target endpoint"}, status_code=response.status_code)

########################################################################################################################


def required_headers_121_kobo(
        url121: str = Header(),
        username121: str = Header(),
        password121: str = Header(),
        kobotoken: str = Header(),
        koboasset: str = Header()):
    return url121, username121, password121, kobotoken, koboasset


@app.post("/create-121-program-from-kobo")
async def create_121_program_from_kobo(request: Request, dependencies=Depends(required_headers_121_kobo)):
    """Utility endpoint to automatically create a 121 Program in 121 from a koboform, including REST Service \n
    Does only support the IFRC server kobonew.ifrc.org \n
    ***NB: if you want to duplicate an endpoint, please also use the Hook ID query param***"""
    
    koboUrl = f"https://kobo.ifrc.org/api/v2/assets/{request.headers['koboasset']}"
    koboheaders = {"Authorization": f"Token {request.headers['kobotoken']}"}
    data_request = requests.get(f'{koboUrl}/?format=json', headers=koboheaders)
    if data_request.status_code >= 400:
        raise HTTPException(
            status_code=data_request.status_code,
            detail=data_request.content.decode("utf-8")
        )
    data = data_request.json()

    survey = pd.DataFrame(data['content']['survey'])
    choices = pd.DataFrame(data['content']['choices'])

    type_mapping = {}
    with open('mappings/kobo121fieldtypes.csv', newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter='\t')
        for row in reader:
            if len(row) == 2:
                type_mapping[row[0]] = row[1]

    mappingdf = pd.read_csv('mappings/kobo121fieldtypes.csv', delimiter='\t')

    CHECKFIELDS = ['validation', 'phase', 'location', 'ngo', 'language', 'titlePortal', 'description',
                'startDate', 'endDate', 'currency', 'distributionFrequency', 'distributionDuration', 'fixedTransferValue',
                'financialServiceProviders', 'targetNrRegistrations', 'tryWhatsAppFirst', 'phoneNumberPlaceholder', 'aboutProgram',
                'fullnameNamingConvention', 'enableMaxPayments', 'phoneNumber','preferredLanguage','maxPayments','fspName']

    # First check if all setup fields are in the xlsform
    FIELDNAMES = survey["name"].to_list()
    MISSINGFIELDS = []
    for checkfield in CHECKFIELDS:
        if checkfield not in FIELDNAMES:
            MISSINGFIELDS.append(checkfield)

    if len(MISSINGFIELDS) != 0:
        print('Missing hidden fields in the template: ', MISSINGFIELDS)

    lookupdict = dict(zip(survey['name'], survey['default']))

    if 'tags'in survey.columns:
        dedupedict =  dict(zip(survey['name'], survey['tags']))

        for key, value in dedupedict.items():
            if isinstance(value, list) and any('dedupe' in item for item in value):
                dedupedict[key] = True
            else:
                dedupedict[key] = False
    else:
        survey['tags'] = False
        dedupedict =  dict(zip(survey['name'], survey['tags']))

    # Create the JSON structure
    data = {
        "published": True,
        "validation": lookupdict['validation'].upper() == 'TRUE',
        "phase": lookupdict['phase'],
        "location": lookupdict['location'],
        "ngo": lookupdict['ngo'],
        "titlePortal": {
            lookupdict['language']: lookupdict['titlePortal']
        },
        "titlePaApp": {
            lookupdict['language']: lookupdict['titlePortal']
        },
        "description": {
            "en": ""
        },
        "startDate": datetime.strptime(lookupdict['startDate'], '%d/%m/%Y').isoformat(),
        "endDate": datetime.strptime(lookupdict['endDate'], '%d/%m/%Y').isoformat(),
        "currency": lookupdict['currency'],
        "distributionFrequency": lookupdict['distributionFrequency'],
        "distributionDuration": int(lookupdict['distributionDuration']),
        "fixedTransferValue": int(lookupdict['fixedTransferValue']),
        "paymentAmountMultiplierFormula": "",
        "financialServiceProviders": [
            {
            "fsp": lookupdict['financialServiceProviders']
            }
        ],
        "targetNrRegistrations": int(lookupdict['targetNrRegistrations']),
        "tryWhatsAppFirst": lookupdict['tryWhatsAppFirst'].upper() == 'TRUE',
        "phoneNumberPlaceholder": lookupdict['phoneNumberPlaceholder'],
        "programCustomAttributes": [],
        "programQuestions": [],
        "aboutProgram": {
            lookupdict['language']: lookupdict['aboutProgram']
        },
        "fullnameNamingConvention": [
            lookupdict['fullnameNamingConvention']
        ],
        "languages": [
            lookupdict['language']
        ],
        "enableMaxPayments": lookupdict['enableMaxPayments'].upper() == 'TRUE',
        "allowEmptyPhoneNumber": False,
        "enableScope": False
    }

    koboConnectHeader = ['fspName', 'preferredLanguage', 'maxPayments']

    for index, row in survey.iterrows():
        if row['type'].split()[0] in mappingdf['kobotype'].tolist() and row['name'] not in CHECKFIELDS:
            koboConnectHeader.append(row['name'])
            question = {
                "name": row['name'],
                "label": {
                    "en": str(row['label'][0])
                },
                "answerType": type_mapping[row['type'].split()[0]],
                "questionType": "standard",
                "options": [],
                "scoring": {},
                "persistence": True,
                "pattern": "",
                "phases": [],
                "editableInPortal": True,
                "export": [
                    "all-people-affected",
                    "included"
                ],
                "shortLabel": {
                    "en": row['name'],
                },
                "duplicateCheck": dedupedict[row['name']],
                "placeholder": ""
            }
            if type_mapping[row['type'].split()[0]] == 'dropdown':
                filtered_df = choices[choices['list_name'] == row['select_from_list_name']]
                for index, row in filtered_df.iterrows():
                    option = {
                        "option": row['name'],
                        "label": {
                            "en": str(row['label'][0])
                        }
                    }
                    question["options"].append(option)
            data["programQuestions"].append(question)
        if row['name'] == 'phoneNumber':
            koboConnectHeader.append('phoneNumber')
            question = {
                "name": 'phoneNumber',
                "label": {
                    "en": 'Phone Number'
                },
                "answerType": "tel",
                "questionType": "standard",
                "options": [],
                "scoring": {},
                "persistence": True,
                "pattern": "",
                "phases": [],
                "editableInPortal": True,
                "export": [
                    "all-people-affected",
                    "included"
                ],
                "shortLabel": {
                    "en": row['name'],
                },
                "duplicateCheck": dedupedict[row['name']],
                "placeholder": ""
            }
            data["programQuestions"].append(question)

    # Create program in 121
    body = {'username': {request.headers['username121']}, 'password': {request.headers['password121']}}
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
        f"{request.headers['url121']}/api/programs",
        headers={'Cookie': f"access_token_general={access_token}"},
        json=data
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.content.decode("utf-8")
        )

    # Create kobo-connect rest service
    restServicePayload = {
        "name": 'Kobo Connect',
        "endpoint": 'https://kobo-connect.azurewebsites.net/kobo-to-121',
        "active": True,
        "email_notification": True,
        "export_type": 'json',
        "settings": {
            "custom_headers": {
            }
        }
    }
    customHeaders = dict(zip(koboConnectHeader, koboConnectHeader))
    restServicePayload['settings']['custom_headers'] = customHeaders

    kobo_response = requests.post(
        f'{koboUrl}/hooks/',
        headers=koboheaders,
        json=restServicePayload
    )

    if kobo_response.status_code == 200 or 201:
        return JSONResponse(content={"message": "Sucess"})
    else:
        return JSONResponse(content={"message": "Failed"}, status_code=response.status_code)

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
