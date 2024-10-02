# pylint: disable=invalid-name
import uvicorn
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
import requests
import pandas as pd
from datetime import datetime, timedelta
import os
from enum import Enum
from dotenv import load_dotenv
from utils.logger import logger
from routes import routes121, routesEspo, routesGeneric, routesKobo


# load environment variables
load_dotenv()
port = os.environ["PORT"]

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


@app.get("/", include_in_schema=False)
async def docs_redirect():
    """Redirect base URL to docs."""
    return RedirectResponse(url="/docs")

# Include routes
app.include_router(routes121.router)
app.include_router(routesEspo.router)
app.include_router(routesGeneric.router)
app.include_router(routesKobo.router)

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
