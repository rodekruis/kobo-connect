import uvicorn
from typing import Union
from fastapi import Security, Depends, FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader, APIKey
from pydantic import BaseModel
from pypdf import PdfReader
from docx import Document as DocxReader
import os
import json
import tiktoken
import openai
import logging
import sys
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s : %(levelname)s : %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("requests_oauthlib").setLevel(logging.WARNING)
from utils import split_string_with_limit, summarize, download_from_azure_storage
from dotenv import load_dotenv
load_dotenv()
openai.api_type = "azure"
openai.api_base = "https://510-openai.openai.azure.com/"
openai.api_version = "2022-12-01"
openai.api_key = os.getenv("OPENAI_API_KEY")

default_instructions = "Explain what this project is about and what is the role of 510. Use maximum 100 words."
admin_key = str(os.getenv('ADMIN_KEY')).strip()
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


# async def get_api_key(api_key_header: str = Security(api_key_header)):
#     if api_key_header == admin_key:
#         return api_key_header
#     else:
#         raise HTTPException(
#             status_code=403, detail="Could not validate credentials"
#         )


# class SummarizePayload(BaseModel):
#     document: str
#     instructions: Union[str, None] = default_instructions
#     max_words: Union[int, None] = 100
#     json_response: Union[bool, None] = False
#     container: Union[str, None] = "510crm"


# load environment variables
port = os.environ["PORT"]

# initialize FastAPI
app = FastAPI(
    title="kobo-connect",
    description="Connect Kobo to anything. \n"
                "Built with love by [NLRC 510](https://www.510.global/). "
                "See [the project on GitHub](https://github.com/rodekruis/kobo-connect) "
                "or [contact us](mailto:support@510.global).",
    version="0.0.1",
    license_info={
        "name": "AGPL-3.0 license",
        "url": "https://www.gnu.org/licenses/agpl-3.0.en.html",
    },
)


@app.get("/", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url='/docs')


@app.post("/kobo")
async def post_submission(request: Request):
    """post a Kobo submission."""
    return JSONResponse(status_code=200, content=request.json())


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(port), reload=True)