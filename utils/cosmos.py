import os
from dotenv import load_dotenv
import azure.cosmos.cosmos_client as cosmos_client

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
