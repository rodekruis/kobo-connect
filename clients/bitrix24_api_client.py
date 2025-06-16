from fastapi import HTTPException
from utils.logger import logger
from utils.utilsKobo import update_submission_status
import requests


class Bitrix24:
    """A client for interacting with the Bitrix24 API."""

    def __init__(self, url):
        if url.endswith("/"):
            url = url[:-1]
        self.url = url

    def request(self, method, bitrix24_url, submission, params=None, logs=None):
        """Make a request to Bitrix24. If the request fails, update submission status in CosmosDB."""

        response = requests.request(method=method, url=bitrix24_url, params=params)

        if response.status_code != 200:
            logger.error(
                f"Failed: Bitrix24 returned {response.status_code} {response.content}",
                extra=logs,
            )
            update_submission_status(submission, "failed", response.content)
            raise HTTPException(
                status_code=response.status_code, detail=f"{response.content}"
            )

        return response.json()
