# pylint: disable=invalid-name
import uvicorn
import time
from fastapi import (
    Security,
    Depends,
    FastAPI,
    APIRouter,
    Request,
    HTTPException,
    Header,
)
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader, APIKey
from pydantic import BaseModel
import re
import requests
import csv
import pandas as pd
from datetime import datetime, timedelta
import os
from azure.cosmos.exceptions import CosmosResourceExistsError
import azure.cosmos.cosmos_client as cosmos_client
from enum import Enum
import base64
import sys
import unicodedata
import io
import json
from dotenv import load_dotenv

from utils.logging import setup_logging

# load environment variables
load_dotenv()
port = os.environ["PORT"]

# Setup logging
setup_logging()

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
    os.getenv("COSMOS_URL"),
    {"masterKey": os.getenv("COSMOS_KEY")},
    user_agent="kobo-connect",
    user_agent_overwrite=True,
)
cosmos_db = client_.get_database_client("kobo-connect")
cosmos_container_client = cosmos_db.get_container_client("kobo-submissions")


@app.get("/", include_in_schema=False)
async def docs_redirect():
    """Redirect base URL to docs."""
    return RedirectResponse(url="/docs")

# Include routes
app.include_router(121_routes.router)
app.include_router(espo_routes.router)
app.include_router(generic_routes.router)
app.include_router(kobo_routes.router)



@app.get("/health")
async def health():
    """Get health of instance."""
    kobo = requests.get(f"https://kobo.ifrc.org/api/v2")
    return JSONResponse(
        status_code=200,
        content={"kobo-connect": 200, "kobo.ifrc.org": kobo.status_code},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(port), reload=True)
