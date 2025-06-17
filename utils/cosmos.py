import os
from dotenv import load_dotenv
import azure.cosmos.cosmos_client as cosmos_client
from azure.cosmos.exceptions import CosmosResourceExistsError
from fastapi import HTTPException

# load environment variables
load_dotenv()

# initialize CosmosDB
client_ = cosmos_client.CosmosClient(
    os.getenv("COSMOS_URL"),
    {"masterKey": os.getenv("COSMOS_KEY")},
    user_agent="kobo-connect",
    user_agent_overwrite=True,
)
cosmos_db = client_.get_database_client("kobo-connect")
cosmos_container_client = cosmos_db.get_container_client("kobo-submissions")


def add_submission(kobo_data):
    """Add submission to CosmosDB. If submission already exists and status is pending, raise HTTPException."""
    submission = {
        "id": str(kobo_data["_uuid"]),
        "uuid": str(kobo_data["formhub/uuid"]),
        "status": "pending",
    }
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
    """Update submission status in CosmosDB. If error_message is not none, raise HTTPException."""
    submission["status"] = status
    submission["error_message"] = error_message
    cosmos_container_client.replace_item(item=str(submission["id"]), body=submission)
    if status == "failed":
        raise HTTPException(status_code=400, detail=error_message)
