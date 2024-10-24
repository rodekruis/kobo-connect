from fastapi import HTTPException, Header
from utils.logger import logger
from utils.utilsKobo import update_submission_status

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
