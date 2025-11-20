from fastapi import APIRouter, Request, Depends, HTTPException
import requests
import re
import os
import io
import json
import csv
import base64
import pandas as pd
from datetime import datetime, timedelta
from fastapi.responses import JSONResponse
from utils.utilsKobo import (
    clean_kobo_data,
    get_attachment_dict,
    required_headers_kobo,
    required_headers_121_kobo,
)
from utils.utils121 import login121, required_headers_121, clean_text
from utils.logger import logger

router = APIRouter()


@router.post("/kobo-to-121", tags=["121"])
async def kobo_to_121(
    request: Request,
    dependencies=Depends(required_headers_121),
    test_mode: bool = False,
):
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
            elif target_field == "fspName":
                payload["programFspConfigurationName"] = kobo_data[
                    kobo_field
                ]
            elif target_field == "programFinancialServiceProviderConfigurationName":
                payload["programFspConfigurationName"] = kobo_data[
                    kobo_field
                ]
            elif (
                kobo_value_url not in attachments.keys() and kobo_data[kobo_field] != ""
            ):
                payload[target_field] = kobo_data[kobo_field]
            else:
                payload[target_field] = attachments[kobo_value_url]["url"]

    payload["referenceId"] = referenceId

    # If test_mode is True, return the payload without posting it
    if test_mode:
        return JSONResponse(status_code=200, content={"payload": payload})

    # Continue with the POST if not in test mode
    access_token = login121(
        request.headers["url121"],
        request.headers["username121"],
        request.headers["password121"],
    )

    url = f"{request.headers['url121']}/api/programs/{programid}/registrations"
    # POST to 121 import endpoint
    import_response = requests.post(
        url,
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


@router.post("/kobo-update-121", tags=["121"])
async def kobo_update_121(
    request: Request,
    dependencies=Depends(required_headers_121),
    test_mode: bool = False,
):
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
        raise HTTPException(
            status_code=400,
            detail=f"'programid' needs to be specified in headers or submission body",
        )
    extra_logs["121_program_id"] = programid

    referenceId = kobo_data["referenceid"]

    # Create API payload body
    intvalues = ["maxPayments", "paymentAmountMultiplier", "inclusionScore"]

    for kobo_field, target_field in request.headers.items():
        payload = {"data": {}, "reason": "Validated during field validation"}
        if kobo_field in kobo_data.keys():
            kobo_value_url = kobo_data[kobo_field].replace(" ", "_")
            kobo_value_url = re.sub(r"[(,),']", "", kobo_value_url)
            if target_field in intvalues:
                payload["data"][target_field] = int(kobo_data[kobo_field])
            elif target_field == "scope":
                payload["data"][target_field] = clean_text(kobo_data[kobo_field])
            elif kobo_value_url not in attachments.keys():
                payload["data"][target_field] = kobo_data[kobo_field]
            else:
                payload["data"][target_field] = attachments[kobo_value_url]["url"]

            if test_mode:
                return JSONResponse(status_code=200, content={"payload": payload})

            access_token = login121(
                request.headers["url121"],
                request.headers["username121"],
                request.headers["password121"],
            )

            # POST to target API
            if target_field != "referenceId":
                response = requests.patch(
                    f"{request.headers['url121']}/api/programs/{programid}/registrations/{referenceId}",
                    headers={"Cookie": f"access_token_general={access_token}"},
                    json=payload,
                )

                target_response = response.content.decode("utf-8")
                logger.info(target_response)

    status_response = requests.patch(
        f"{request.headers['url121']}/api/programs/{programid}/registrations/status?dryRun=false&filter.referenceId=$in:{referenceId}",
        headers={"Cookie": f"access_token_general={access_token}"},
        json={"status": "validated"},
    )

    if status_response.status_code != 202:
        raise HTTPException(
            status_code=response.status_code,
            detail="Failed to set status of PA to validated",
        )

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


########################################################################################################################


@router.post("/create-offline-validation-form", tags=["121"])
async def create_offline_validation_form(
    request: Request,
    unique_identifier: str,
    dependencies=Depends(required_headers_kobo),
):
    """
    Create and deploy an offline validation form on KoboToolbox.
    This endpoint creates a new KoboToolbox form based on an existing form,
    modifies it for offline validation, and deploys it. It also sets up a
    Kobo Connect REST service for the new form.
    """
    koboUrl = "https://kobo.ifrc.org/api/v2/assets/"
    koboGetUrl = koboUrl + request.headers["koboasset"]
    koboheaders = {"Authorization": f"Token {request.headers['kobotoken']}"}
    data_request = requests.get(f"{koboGetUrl}/?format=json", headers=koboheaders)
    if data_request.status_code >= 400:
        logger.error(f"Failed to get Kobo form: {data_request.content.decode('utf-8')}")
        raise HTTPException(
            status_code=data_request.status_code,
            detail=data_request.content.decode("utf-8"),
        )
    data = data_request.json()

    data["name"] = data["name"] + " - Offline Validation"

    # Reorder survey to have the target question first
    question_types = {
        "integer",
        "decimal",
        "range",
        "text",
        "select_one",
        "select_multiple",
        "select_one_from_file",
        "select_multiple_from_file",
        "rank",
        "note",
        "date",
        "time",
        "dateTime",
        "barcode",
        "calculate",
        "acknowledge",
        "hidden",
        "xml-external",
    }
    group_types = {"begin_group", "end_group"}
    no_pulldata_types = {
        "geopoint",
        "geotrace",
        "geoshape",
        "image",
        "audio",
        "background-audio",
        "video",
        "file",
    }

    survey = data["content"]["survey"]

    known_type_questions = []
    unknown_type_questions = []
    target_question = None
    customKoboRestHeaders = {}

    for question in survey:
        if question.get("name") == unique_identifier:
            if "relevant" in question:
                del question["relevant"]
            question["required"] = True
            question["$xpath"] = unique_identifier
            target_question = question
        elif question.get("type") in question_types:
            calculation = f"pulldata('ValidationDataFrom121','{question.get('name')}','{unique_identifier}',${{{unique_identifier}}})"
            question["calculation"] = calculation
            known_type_questions.append(question)
            customKoboRestHeaders[question.get("name")] = question.get("name")
        elif question.get("type") in group_types:
            known_type_questions.append(question)
        elif question.get("type") in no_pulldata_types:
            logger.info(f"Not included question: {question.get('name')}")
        else:
            unknown_type_questions.append(question)

    if target_question:
        # Reconstruct survey: unknown type questions first, then target question, then known type questions
        data["content"]["survey"] = (
            unknown_type_questions + [target_question] + known_type_questions
        )

    data["content"]["survey"].append(
        {
            "name": "referenceId",
            "type": "hidden",
            "$xpath": "referenceId",
            "$autoname": "referenceId",
            "calculation": f"pulldata('ValidationDataFrom121','referenceId','{unique_identifier}',${{{unique_identifier}}})",
        }
    )

    # create new form
    post_validation_form = requests.post(
        koboUrl + "?format=json", headers=koboheaders, json=data
    )
    if post_validation_form.status_code >= 400:
        logger.error(
            f"Failed to create new Kobo form: {post_validation_form.content.decode('utf-8')}"
        )
        raise HTTPException(
            status_code=post_validation_form.status_code,
            detail=post_validation_form.content.decode("utf-8"),
        )

    formId = post_validation_form.json()["uid"]
    logger.info(f"Created new Kobo form with ID: {formId}")

    # Deploy the Kobo form
    deploy_url = f"{koboUrl}{formId}/deployment/"
    deploy_payload = {"active": True}

    deploy_response = requests.post(
        deploy_url, headers=koboheaders, json=deploy_payload
    )
    if deploy_response.status_code >= 400:
        logger.error(
            f"Failed to deploy Kobo form: {deploy_response.content.decode('utf-8')}"
        )
        raise HTTPException(
            status_code=deploy_response.status_code,
            detail=deploy_response.content.decode("utf-8"),
        )

    if 200 <= deploy_response.status_code <= 299:
        # Create kobo-connect rest service
        restServicePayload = {
            "name": "Kobo Connect (kobo-update-121)",
            "endpoint": "https://kobo-connect.azurewebsites.net/kobo-update-121",
            "active": True,
            "email_notification": True,
            "export_type": "json",
            "settings": {"custom_headers": {}},
        }

        customKoboRestHeaders["referenceId"] = "referenceId"
        customKoboRestHeaders["url121"] = "https://placeholder.121.global"
        customKoboRestHeaders["username121"] = "userplaceholder"
        customKoboRestHeaders["password121"] = "passwordplaceholder"
        customKoboRestHeaders["programid"] = "programidplaceholder(integer)"

        restServicePayload["settings"]["custom_headers"] = customKoboRestHeaders

        kobo_response = requests.post(
            f"{koboUrl}{formId}/hooks/", headers=koboheaders, json=restServicePayload
        )

    if kobo_response.status_code == 200 or 201:
        logger.info("Validation form created and deployed successfully")
        return JSONResponse({"message": "Validation form created successfully"})
    else:
        logger.error(
            f"Failed to create Kobo Connect rest service: {kobo_response.content.decode('utf-8')}"
        )
        return JSONResponse(
            content={"message": "Failed"}, status_code=kobo_response.status_code
        )


########################################################################################################################


@router.get("/121-program", tags=["121"])
async def create_121_program_from_kobo(
    request: Request,
    dependencies=Depends(required_headers_kobo),
    test_mode: bool = False,
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
        "location",
        "ngo",
        "language",
        "titlePortal",
        "startDate",
        "endDate",
        "currency",
        "distributionFrequency",
        "distributionDuration",
        "fixedTransferValue",
        "targetNrRegistrations",
        "tryWhatsAppFirst",
        "aboutProgram",
        "fullnameNamingConvention",
        "enableMaxPayments",
        "phoneNumber",
        "preferredLanguage",
        "budget",
        "maxPayments",
    ]

    # First check if all setup fields are in the xlsform
    FIELDNAMES = survey["name"].to_list()
    MISSINGFIELDS = []
    for checkfield in CHECKFIELDS:
        if checkfield not in FIELDNAMES:
            MISSINGFIELDS.append(checkfield)
    if (
        "fspName" not in FIELDNAMES
        and "programFinancialServiceProviderConfigurationName" not in FIELDNAMES
        and "programFspConfigurationName" not in FIELDNAMES
    ):
        MISSINGFIELDS.append(
            "programFspConfigurationName or fspName or programFinancialServiceProviderConfigurationName"
        )

    if len(MISSINGFIELDS) != 0:
        print("Missing hidden fields in the template: ", MISSINGFIELDS)
        raise HTTPException(
            status_code=400,
            detail=f"Missing required keys in kobo form: {MISSINGFIELDS}",
        )

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

    try:
        start_date = datetime.strptime(lookupdict["startDate"], "%d/%m/%Y").isoformat()
        end_date = datetime.strptime(lookupdict["endDate"], "%d/%m/%Y").isoformat()
    except ValueError:
        start_date = datetime.now().isoformat()
        end_date = (datetime.now() + timedelta(days=90)).isoformat()

    # Create the JSON structure
    try:
        data = {
            "published": True,
            "validation": lookupdict.get("validation", "FALSE").upper() == "TRUE",
            "location": lookupdict.get("location", ""),
            "ngo": lookupdict.get("ngo", ""),
            "titlePortal": {lookupdict.get("language", "en"): lookupdict.get("titlePortal", "")},
            "titlePaApp": {lookupdict.get("language", "en"): lookupdict.get("titlePortal", "")},
            "description": {"en": ""},
            "startDate": start_date,
            "endDate": end_date,
            "currency": lookupdict.get("currency", ""),
            "distributionFrequency": lookupdict.get("distributionFrequency", ""),
            "distributionDuration": int(lookupdict.get("distributionDuration", 0)),
            "fixedTransferValue": int(lookupdict.get("fixedTransferValue", 0)),
            "paymentAmountMultiplierFormula": "",
            "targetNrRegistrations": int(lookupdict.get("targetNrRegistrations", 0)),
            "tryWhatsAppFirst": lookupdict.get("tryWhatsAppFirst", "FALSE").upper() == "TRUE",
            "programCustomAttributes": [],
            "programRegistrationAttributes": [],
            "aboutProgram": {lookupdict.get("language", "en"): lookupdict.get("aboutProgram", "")},
            "fullnameNamingConvention": [lookupdict.get("fullnameNamingConvention", "")],
            "languages": [lookupdict.get("language", "en")],
            "enableMaxPayments": lookupdict.get("enableMaxPayments", "FALSE").upper() == "TRUE",
            "allowEmptyPhoneNumber": False,
            "enableScope": False,
        }
    except (ValueError, TypeError) as e:
        logger.error(f"Error creating data structure: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid data format in Kobo form: {str(e)}"
        )
    except KeyError as e:
        logger.error(f"Missing required field: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Missing required field in Kobo form: {str(e)}"
        )

    koboConnectHeader = ["fspName", "preferredLanguage", "maxPayments"]

    for index, row in survey.iterrows():
        if (
            row["type"].split()[0] in mappingdf["kobotype"].tolist()
            and row["name"] not in CHECKFIELDS
            and row["name"] not in fspquestions
            and row["name"]
            not in ["fspName", "programFinancialServiceProviderConfigurationName", "programFspConfigurationName", "phase", "phoneNumberPlaceHolder", "FinancialServiceProviders", "description"]
        ):
            koboConnectHeader.append(row["name"])
            question = {
                "name": row["name"],
                # check if label exists, otherwise use name:
                "label": {
                    "en": (
                        str(row["label"][0])
                        if not isinstance(row["label"], float)
                        else row["name"]
                    )
                },
                "type": type_mapping[row["type"].split()[0]],
                "options": [],
                "scoring": {},
                "persistence": True,
                "pattern": "",
                "phases": [],
                "editableInPortal": True,
                "export": ["registrations"],
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
            data["programRegistrationAttributes"].append(question)
        if row["name"] == "phoneNumber":
            koboConnectHeader.append("phoneNumber")
            question = {
                "name": "phoneNumber",
                "label": {"en": "Phone Number"},
                "type": "tel",
                "options": [],
                "scoring": {},
                "persistence": True,
                "pattern": "",
                "phases": [],
                "editableInPortal": True,
                "export": ["registrations"],
                "shortLabel": {
                    "en": row["name"],
                },
                "duplicateCheck": dedupedict[row["name"]],
                "placeholder": "",
            }
            data["programRegistrationAttributes"].append(question)

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


########################################################################################################################


@router.post("/update-kobo-csv", tags=["121"])
async def prepare_kobo_validation(
    request: Request,
    programId: int,
    kobousername: str,
    delay: int = 0,
    dependencies=Depends(required_headers_121_kobo),
):
    """
    Prepare Kobo validation by fetching data from 121 platform,
    converting it to CSV, and uploading to Kobo.
    """

    # Delay execution if delay is set
    if delay > 0:
        time.sleep(delay)

    access_token = login121(
        request.headers["url121"],
        request.headers["username121"],
        request.headers["password121"],
    )

    # Fetch data from 121 platform
    response = requests.get(
        f"{request.headers['url121']}/api/programs/{programId}/metrics/export-list/registrations",
        headers={"Cookie": f"access_token_general={access_token}"},
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail="Failed to fetch data from 121 platform",
        )

    # Extract the data from the JSON response
    json_response = response.json()
    data = json_response.get("data", [])  # Access the 'data' array from the response

    project = requests.get(
        f"{request.headers['url121']}/api/programs/{programId}?formatProgramReturnDto=true",
        headers={"Cookie": f"access_token_general={access_token}"},
    )

    if project.status_code != 200:
        raise HTTPException(
            status_code=project.status_code,
            detail="Failed to fetch project data from 121 platform",
        )

    projectdata = project.json()

    # Build a mapping of dropdown fields: field_name → {label → option}
    dropdown_mappings = {}
    for attr in projectdata.get("programRegistrationAttributes", []):
        if attr.get("type") == "dropdown":
            field_name = attr["name"]
            options = attr.get("options", [])
            label_to_option = {
                option["label"]["en"]: option["option"]
                for option in options
                if "label" in option and "en" in option["label"]
            }
            dropdown_mappings[field_name] = label_to_option

    # Replace dropdown labels with their option values in all relevant fields
    for reg in data:
        for field, label_to_option in dropdown_mappings.items():
            label = reg.get(field)
            if label and label in label_to_option:
                reg[field] = label_to_option[label]

    # Update the original response with the modified data
    json_response["data"] = data
    data = json_response

    # Convert JSON to CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Ensure we have data to process
    if data and "data" in data and len(data["data"]) > 0:
        # Get the keys (column names) from the last row
        fieldnames = list(data["data"][-1].keys())

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
