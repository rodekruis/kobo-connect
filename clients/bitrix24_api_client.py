from fastapi import HTTPException
from utils.logger import logger
from utils.cosmos import update_submission_status
import requests


class Bitrix24:
    """A client for interacting with the Bitrix24 API."""

    def __init__(self, url, key):
        if url.endswith("/"):
            url = url[:-1]
        self.url = url + "/rest/1/" + key + "/"

    def request(self, method, endpoint, submission, params=None, logs=None):
        """Make a request to Bitrix24. If the request fails, update submission status in CosmosDB."""

        response = requests.request(
            method=method, url=self.url + endpoint, params=params
        )

        if response.status_code != 200:
            print(
                f"Failed: Bitrix24 returned {response.status_code} {response.content}"
            )
            logger.error(
                f"Failed: Bitrix24 returned {response.status_code} {response.content}",
                extra=logs,
            )
            # update_submission_status(submission, "failed", response.content)
            raise HTTPException(
                status_code=response.status_code, detail=f"{response.content}"
            )

        return response.json()
