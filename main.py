import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse, JSONResponse
import requests
import os
from dotenv import load_dotenv
from routes import routes121, routesEspo, routesGeneric, routesKobo

# load environment variables
load_dotenv()
port = os.environ["PORT"]

# Set up logs export to Azure Application Insights
logger_provider = LoggerProvider()
set_logger_provider(logger_provider)
exporter = AzureMonitorLogExporter(
    connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

# Attach LoggingHandler to root logger
handler = LoggingHandler()
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.NOTSET)
logger = logging.getLogger(__name__)

# Silence noisy loggers
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("requests_oauthlib").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.ERROR)

# initialize FastAPI
app = FastAPI(
    title="kobo-connect",
    description="Connect Kobo to anything. \n"
    "Built with love by [NLRC 510](https://www.510.global/). "
    "See [the project on GitHub](https://github.com/rodekruis/kobo-connect) "
    "or [contact us](mailto:support@510.global).",
    version="0.0.3",
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
