import os
from dotenv import load_dotenv
import azure.cosmos.cosmos_client as cosmos_client
from azure.cosmos.exceptions import CosmosResourceExistsError
from fastapi import HTTPException

# load environment variables
load_dotenv()

cosmos_container_client = None


def get_cosmos_container_client():
    """Get the configured CosmosDB container client."""
    global cosmos_container_client

    if cosmos_container_client is None:
        cosmos_url = os.getenv("COSMOS_URL")
        cosmos_key = os.getenv("COSMOS_KEY")
        if not cosmos_url or not cosmos_key:
            raise HTTPException(
                status_code=500,
                detail="CosmosDB is not configured.",
            )

        client_ = cosmos_client.CosmosClient(
            cosmos_url,
            {"masterKey": cosmos_key},
            user_agent="kobo-connect",
            user_agent_overwrite=True,
        )
        cosmos_db = client_.get_database_client("kobo-connect")
        cosmos_container_client = cosmos_db.get_container_client("kobo-submissions")

    return cosmos_container_client


def add_submission(kobo_data):
    """Add submission to CosmosDB. If submission already exists and status is pending, raise HTTPException."""
    submission = {
        "id": str(kobo_data["_uuid"]),
        "uuid": str(kobo_data["formhub/uuid"]),
        "status": "pending",
    }
    cosmos_container_client = get_cosmos_container_client()
    try:
        submission = cosmos_container_client.create_item(body=submission)
    except CosmosResourceExistsError:
        submission = cosmos_container_client.read_item(
            item=str(kobo_data["_uuid"]),
            partition_key=str(kobo_data["formhub/uuid"]),
        )
        if submission["status"] == "pending":
            raise HTTPException(
                status_code=400, detail="Submission is still being processed."
            )
    return submission


def update_submission_status(submission, status, error_message=None):
    """Update submission status in CosmosDB."""
    submission["status"] = status
    submission["error_message"] = error_message
    cosmos_container_client = get_cosmos_container_client()
    cosmos_container_client.replace_item(item=str(submission["id"]), body=submission)
