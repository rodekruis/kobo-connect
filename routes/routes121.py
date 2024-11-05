from fastapi import APIRouter, Request, Depends, HTTPException
import requests
import re
import os
import csv
import pandas as pd
from datetime import datetime, timedelta
from fastapi.responses import JSONResponse
from utils.utilsKobo import clean_kobo_data, get_attachment_dict, required_headers_kobo
from utils.utils121 import login121, required_headers_121, clean_text
from utils.logger import logger

router = APIRouter()

@router.post("/kobo-to-121")
async def kobo_to_121(request: Request, dependencies=Depends(required_headers_121), test_mode: bool = False):
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
    extra_logs["121_program_id"] = programid

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

    # If test_mode is True, return the payload without posting it
    if test_mode:
        return JSONResponse(status_code=200, content={"payload": payload})

    # Continue with the POST if not in test mode
    access_token = login121(request.headers["url121"], request.headers["username121"], request.headers["password121"])

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

@router.post("/kobo-update-121")
async def kobo_update_121(request: Request, dependencies=Depends(required_headers_121), test_mode: bool = False):
    """Update a 121 record from a Kobo submission"""

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
    extra_logs["121_program_id"] = programid

    referenceId = kobo_data['referenceid']

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

            if test_mode:
                return JSONResponse(status_code=200, content={"payload": payload})
            
            access_token = login121(request.headers["url121"], request.headers["username121"], request.headers["password121"])

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
    
    update_response_message = status_response.content.decode("utf-8")
    if 200 <= status_response.status_code <= 299:
        logger.info(
            f"Success: 121 update returned {status_response.status_code} {update_response_message}",
            extra=extra_logs,
        )
    elif status_response.status_code >= 400:
        logger.error(
            f"Failed: 121 update returned {status_response.status_code} {update_response_message}",
            extra=extra_logs,
        )
        raise HTTPException(
            status_code=status_response.status_code, detail=update_response_message
        )
    else:
        logger.warning(
            f"121 update returned {status_response.status_code} {update_response_message}",
            extra=extra_logs,
        )

    return JSONResponse(
        status_code=status_response.status_code, content=update_response_message
    )

###########
@router.get("/121-program")
async def create_121_program_from_kobo(
    request: Request, dependencies=Depends(required_headers_kobo), test_mode: bool = False
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
                # check if label exists, otherwise use name:
                "label": {"en": str(row["label"][0]) if not isinstance(row["label"], float) else row["name"]},
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

    if test_mode:
        return JSONResponse(status_code=200, content=data)
    
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

