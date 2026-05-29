from __future__ import annotations

from typing import Any, NamedTuple

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from utils.cosmos import add_submission, update_submission_status
from utils.utilsKobo import (
    clean_kobo_data,
    get_attachment_dict,
    get_kobo_attachment,
)
from utils.utilsEspo import espo_request, required_headers_espocrm
from utils.logger import logger
from clients.espo_api_client import EspoAPI
import os
import re
import base64

router = APIRouter()


class FieldType(NamedTuple):
    """Parsed field-type prefix from a Kobo header key."""

    field: str
    multi: bool
    repeat: bool
    repeat_index: int
    repeat_question: str


class RelatedEntityResult(NamedTuple):
    """Result of a related entity lookup in EspoCRM."""

    record_id: str | None
    entity_name: str | None
    error: str | None


class TargetField(NamedTuple):
    """Parsed target field mapping from a Kobo header value."""

    entity: str
    field: str
    related: bool
    linked_field: str
    related_entity: str
    related_entity_field: str


def fail_response(
    submission: dict[str, Any], error_message: str, extra_logs: dict[str, Any]
) -> JSONResponse:
    """Log error, mark submission as failed, and return a 400 JSONResponse."""
    logger.error(f"Failed: {error_message}", extra=extra_logs)
    update_submission_status(submission, "failed", error_message)
    return JSONResponse(status_code=400, content={"detail": error_message})


def parse_field_type(kobo_field: str) -> FieldType:
    """Parse a kobo_field header key to extract its type prefix and actual field name.

    Kobo field header keys can have a dot-separated prefix indicating special handling:

    - "fieldName" (no prefix): plain field, value is used as-is.
      Example: "sector" → field 'sector', plain value.

    - "multi.fieldName": multi-select field, value is split by spaces into a list.
      Example: "multi.services" → field 'services', value split into list.

    - "repeat.fieldName.index.question": repeat group field, value is extracted
      from the repeat group array at the given index and question key.
      Example: "repeat.household.0.name" → field 'household', index 0, question 'name'.
    """
    if "multi." in kobo_field:
        return FieldType(
            field=kobo_field.split(".")[1],
            multi=True,
            repeat=False,
            repeat_index=0,
            repeat_question="",
        )
    if "repeat." in kobo_field:
        parts = kobo_field.split(".")
        return FieldType(
            field=parts[1],
            multi=False,
            repeat=True,
            repeat_index=int(parts[2]),
            repeat_question=parts[3],
        )
    return FieldType(
        field=kobo_field,
        multi=False,
        repeat=False,
        repeat_index=0,
        repeat_question="",
    )


def parse_target_field(
    target_field: str,
) -> TargetField | None:
    """Parse a target_field header value into its components.

    Target fields are dot-separated strings that define how a Kobo field maps to EspoCRM.
    Supported formats:

    - "Entity.field" (2 parts): direct field mapping.
      Example: "CFeedbackData.topic" → set field 'topic' on entity 'CFeedbackData'.

    - "Entity.linkedField.lookupField" (3 parts): related entity lookup.
      Example: "CFeedbackData.codingLevel1.name" → find a 'CodingLevel1' record where
      'name' equals the Kobo value, then link it via 'codingLevel1Id' on 'CFeedbackData'.
      The related entity name is derived by capitalizing the first letter of linkedField.

    Returns a TargetField or None if the format is unrecognized (e.g. 1 or 4+ parts).
    """
    parts = target_field.split(".")

    if len(parts) == 2:
        return TargetField(
            entity=parts[0],
            field=parts[1],
            related=False,
            linked_field="",
            related_entity="",
            related_entity_field="",
        )

    if len(parts) == 3:
        linked_field = parts[1]
        related_entity = linked_field[0].upper() + linked_field[1:]
        return TargetField(
            entity=parts[0],
            field=target_field,
            related=True,
            linked_field=linked_field,
            related_entity=related_entity,
            related_entity_field=parts[2],
        )

    return None


def get_kobo_value(
    kobo_data: dict[str, Any],
    ft: FieldType,
) -> tuple[Any, bool]:
    """Extract a value from the Kobo submission based on field type.

    Returns (value, skip). skip is True when the value cannot be resolved
    (e.g. repeat index out of range or repeat question key missing),
    indicating the caller should silently skip this field.
    """
    if ft.multi:
        return kobo_data[ft.field].split(" "), False

    if ft.repeat:
        if ft.repeat_index < 0 or ft.repeat_index >= len(kobo_data[ft.field]):
            return None, True
        kobo_data[ft.field][ft.repeat_index] = clean_kobo_data(
            kobo_data[ft.field][ft.repeat_index]
        )
        if ft.repeat_question not in kobo_data[ft.field][ft.repeat_index]:
            return None, True
        return kobo_data[ft.field][ft.repeat_index][ft.repeat_question], False

    return kobo_data[ft.field], False


def resolve_related_entity(
    client: EspoAPI,
    related_entity: str,
    related_entity_field: str,
    kobo_value: Any,
    extra_logs: dict[str, Any],
) -> RelatedEntityResult:
    """Look up a related entity record in EspoCRM by field value.

    EspoCRM custom entities are prefixed with 'C' (e.g. CodingLevel1 → CCodingLevel1).
    If the initial lookup fails, retries with the 'C' prefix automatically.

    Returns a RelatedEntityResult:
    - On success: record_id is set, error is None.
    - Entity not found: entity_name is None, error describes the failure.
    - Ambiguous match (!= 1 record): entity_name is set, error describes the ambiguity.
    """
    params = {
        "where": [
            {"type": "equals", "attribute": related_entity_field, "value": kobo_value}
        ]
    }

    # Try the entity name as-is
    response = espo_request(
        client, "GET", related_entity, params=params, logs=extra_logs
    )

    # Retry with "C" prefix for EspoCRM custom entities
    if response is None:
        related_entity_c = "C" + related_entity
        logger.info(
            f"Entity '{related_entity}' not found, retrying with '{related_entity_c}'",
            extra=extra_logs,
        )
        response = espo_request(
            client, "GET", related_entity_c, params=params, logs=extra_logs
        )
        if response is not None:
            related_entity = related_entity_c

    if response is None:
        return RelatedEntityResult(
            record_id=None,
            entity_name=None,
            error=f"Related entity '{related_entity}' does not exist in EspoCRM "
            f"(also tried 'C{related_entity}')",
        )

    records = response["list"]
    if len(records) != 1:
        return RelatedEntityResult(
            record_id=None,
            entity_name=related_entity,
            error=f"Found {len(records)} records of entity {related_entity} "
            f"with field {related_entity_field} equal to {kobo_value}: record must be unique",
        )

    return RelatedEntityResult(
        record_id=records[0]["id"], entity_name=related_entity, error=None
    )


def upload_attachment(
    client: EspoAPI,
    kobo_field: str,
    kobo_value: Any,
    file_url: str,
    mimetype: str,
    target_entity: str,
    target_field: str,
    kobotoken: str | None,
    extra_logs: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Download a Kobo attachment and upload it to EspoCRM.

    Returns (attachment_id, None) on success, or (None, error_message) on failure.
    """
    if not kobotoken:
        return (
            None,
            "'kobotoken' needs to be specified in headers to upload attachments to EspoCRM",
        )

    logger.info(f"Getting attachment of field: {kobo_field}", extra=extra_logs)
    file = get_kobo_attachment(file_url, kobotoken)

    if not file:
        return None, f"Attachment retrieval failed for field: {kobo_field}"

    logger.info(
        f"Successfully retrieved attachment of field: {kobo_field}", extra=extra_logs
    )

    file_b64 = base64.b64encode(file).decode("utf8")
    attachment_payload = {
        "name": kobo_value,
        "type": mimetype,
        "role": "Attachment",
        "relatedType": target_entity,
        "field": target_field,
        "file": f"data:{mimetype};base64,{file_b64}",
    }
    record = espo_request(
        client,
        "POST",
        "Attachment",
        params=attachment_payload,
        logs=extra_logs,
    )

    if record is None:
        return None, f"Failed to upload attachment for field: {kobo_field}"

    return record["id"], None


@router.post("/kobo-to-espocrm", tags=["EspoCRM"])
async def kobo_to_espocrm(
    request: Request, dependencies=Depends(required_headers_espocrm)
):
    """Receive a Kobo submission and forward its fields to EspoCRM.

    The mapping between Kobo fields and EspoCRM entities/fields is defined via
    HTTP headers on the request. Each header key is a Kobo field name (optionally
    prefixed with ``multi.`` or ``repeat.``) and the value is a dot-separated
    EspoCRM target (e.g. ``Entity.field`` or ``Entity.linkedField.lookupField``).

    Special headers:
        targeturl / targetkey: EspoCRM instance URL and API key.
        kobotoken / koboasset: Kobo credentials for attachment retrieval.
        updaterecordby: ``Entity.field`` — update an existing record instead of
            creating a new one.

    Flow:
        1. Validate the submission and check for duplicates via Cosmos DB.
        2. Parse headers to build a field mapping.
        3. Resolve related entities and upload attachments as needed.
        4. Create or update records in EspoCRM.
    """

    kobo_data = await request.json()
    extra_logs = {"environment": os.getenv("ENV")}

    # Validate submission
    try:
        extra_logs["kobo_form_id"] = str(kobo_data["_xform_id_string"])
        extra_logs["kobo_form_version"] = str(kobo_data["__version__"])
        extra_logs["kobo_submission_id"] = str(kobo_data["_id"])
    except KeyError:
        return JSONResponse(
            status_code=422, content={"detail": "Not a valid Kobo submission"}
        )

    logger.info("Successfully received submission from Kobo", extra=extra_logs)

    # Check for duplicate submissions
    submission = add_submission(kobo_data)
    logger.info(
        "Successfully created/retrieved submission from Cosmos DB", extra=extra_logs
    )

    if submission["status"] == "success":
        logger.info(
            "Submission has already been successfully processed", extra=extra_logs
        )
        return JSONResponse(
            status_code=200,
            content={"detail": "Submission has already been successfully processed"},
        )

    kobo_data = clean_kobo_data(kobo_data)

    # Check if submission should be skipped
    if kobo_data.get("skipconnect") == "1":
        logger.info("Skipping submission", extra=extra_logs)
        return JSONResponse(status_code=200, content={"message": "Skipping submission"})

    # Initialize EspoCRM client
    kobotoken = request.headers.get("kobotoken")
    koboasset = request.headers.get("koboasset")
    client = EspoAPI(request.headers["targeturl"], request.headers["targetkey"])

    # Get attachment URLs
    logger.info("Getting attachment urls", extra=extra_logs)
    attachments = get_attachment_dict(kobo_data, kobotoken, koboasset)
    logger.info(
        f"Successfully retrieved urls of {len(attachments)} attachments",
        extra=extra_logs,
    )

    # Parse update-record-by header: if set, update an existing record
    # (matched by field value) instead of creating a new one
    update_record_payload: dict[str, dict[str, str]] = {}
    if "updaterecordby" in request.headers and "updaterecordby" in kobo_data:
        value = kobo_data["updaterecordby"]
        if value:
            entity, field = request.headers["updaterecordby"].split(".")
            update_record_payload[entity] = {"field": field, "value": value}
        kobo_data.pop("updaterecordby")

    # Build API payload by mapping Kobo fields to EspoCRM fields
    payload: dict[str, dict[str, Any]] = {}

    for kobo_field, target_field in request.headers.items():

        # Parse field type prefix
        ft = parse_field_type(kobo_field)

        if ft.field not in kobo_data:
            continue

        # Parse target field structure
        parsed = parse_target_field(target_field)
        if parsed is None:
            continue

        target_entity = parsed.entity
        target_field = parsed.field

        if target_entity not in payload:
            payload[target_entity] = {}

        # Extract value from submission
        kobo_value, skip = get_kobo_value(kobo_data, ft)
        if skip:
            continue

        # Resolve related entity lookup
        if parsed.related:
            result = resolve_related_entity(
                client,
                parsed.related_entity,
                parsed.related_entity_field,
                kobo_value,
                extra_logs,
            )
            if result.error:
                if result.entity_name is None:
                    # Entity doesn't exist at all — skip this field
                    continue
                return fail_response(submission, result.error, extra_logs)
            kobo_value = result.record_id
            target_field = parsed.linked_field + "Id"

        # Normalize value to match attachment filenames (strip parens/quotes, underscores for spaces)
        kobo_value_url = re.sub(r"[(,)']", "", str(kobo_value).replace(" ", "_"))

        if kobo_value_url not in attachments:
            payload[target_entity][target_field] = kobo_value
        else:
            attachment_info = attachments[kobo_value_url]
            attachment_id, error = upload_attachment(
                client,
                kobo_field,
                kobo_value,
                attachment_info["url"],
                attachment_info["mimetype"],
                target_entity,
                target_field,
                kobotoken,
                extra_logs,
            )
            if error:
                return fail_response(submission, error, extra_logs)
            payload[target_entity][f"{target_field}Id"] = attachment_id

    # Validate payload
    if not payload:
        return fail_response(
            submission,
            "No fields found in submission or no entities found in headers",
            extra_logs,
        )

    # Send payload to EspoCRM
    target_response: dict[str, Any] = {}

    for entity_name, entity_payload in payload.items():

        if entity_name not in update_record_payload:
            # Create new record
            response = espo_request(
                client,
                "POST",
                entity_name,
                params=entity_payload,
                logs=extra_logs,
            )
            if response is None:
                return fail_response(
                    submission,
                    f"Failed to create record in entity '{entity_name}'",
                    extra_logs,
                )
        else:
            # Find and update existing record
            search_params = {
                "where": [
                    {
                        "type": "contains",
                        "attribute": update_record_payload[entity_name]["field"],
                        "value": update_record_payload[entity_name]["value"],
                    }
                ]
            }
            find_response = espo_request(
                client,
                "GET",
                entity_name,
                params=search_params,
                logs=extra_logs,
            )
            if find_response is None:
                return fail_response(
                    submission,
                    f"Failed to search for records in entity '{entity_name}'",
                    extra_logs,
                )

            records = find_response["list"]
            if len(records) != 1:
                return fail_response(
                    submission,
                    f"Found {len(records)} records of entity {entity_name} "
                    f"with field {update_record_payload[entity_name]['field']} "
                    f"equal to {update_record_payload[entity_name]['value']}: record must be unique",
                    extra_logs,
                )

            response = espo_request(
                client,
                "PUT",
                f"{entity_name}/{records[0]['id']}",
                params=entity_payload,
                logs=extra_logs,
            )
            if response is None:
                return fail_response(
                    submission,
                    f"Failed to update record in entity '{entity_name}'",
                    extra_logs,
                )

        if "id" not in response:
            return fail_response(
                submission,
                f"Unexpected response from EspoCRM for entity '{entity_name}': missing 'id'",
                extra_logs,
            )

        target_response[entity_name] = response

    logger.info("Success", extra=extra_logs)
    update_submission_status(submission, "success")
    return JSONResponse(status_code=200, content=target_response)
