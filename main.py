import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse, JSONResponse
import requests
import os
from dotenv import load_dotenv
from utils.logger import logger
from routes import routes121, routesEspo, routesGeneric, routesKobo, routesBitrix24

# load environment variables
load_dotenv()
port = os.environ["PORT"]

tags_metadata = [
    {
        "name": "121",
        "description": "Integration with 121.",
    },
    {
        "name": "EspoCRM",
        "description": "Integration with EspoCRM.",
    },
    {
        "name": "Bitrix24",
        "description": "Integration with Bitrix24.",
    },
    {
        "name": "Kobo",
        "description": "Extensions to Kobo.",
    },
]

# initialize FastAPI
app = FastAPI(
    title="kobo-connect",
    description="Connect Kobo to anything. \n"
    "Built with love by [NLRC 510](https://www.510.global/). "
    "See [the project on GitHub](https://github.com/rodekruis/kobo-connect) "
    "or [contact us](mailto:support@510.global).",
    version="0.0.4",
    license_info={
        "name": "AGPL-3.0 license",
        "url": "https://www.gnu.org/licenses/agpl-3.0.en.html",
    },
    openapi_tags=tags_metadata,
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
app.include_router(routesBitrix24.router)


@app.get("/health")
async def health():
    """Get health of instance."""
    logger.info("Health check initiated")
    try:
        kobo = requests.get(f"https://kobo.ifrc.org/api/v2", timeout=10)
        logger.info(f"Kobo API health check completed with status: {kobo.status_code}")
        return JSONResponse(
            status_code=200,
            content={"kobo-connect": 200, "kobo.ifrc.org": kobo.status_code},
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Kobo API health check failed: {str(e)}")
        return JSONResponse(
            status_code=200,
            content={"kobo-connect": 200, "kobo.ifrc.org": "unavailable"},
        )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(port), reload=True)
