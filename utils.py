import os
import tiktoken
import openai
from fastapi import HTTPException
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError
from dotenv import load_dotenv
load_dotenv()
openai.api_type = "azure"
openai.api_base = "https://510-openai.openai.azure.com/"
openai.api_version = "2022-12-01"
openai.api_key = os.getenv("OPENAI_API_KEY")


def split_string_with_limit(text: str, limit: int, encoding: tiktoken.Encoding) -> list:
    """Split a string into parts of given number of tokens without breaking words.

    Args:
        text (str): Text to split.
        limit (int): Maximum number of tokens per part.
        encoding (tiktoken.Encoding): Encoding to use for tokenization.

    Returns:
        list[str]: List of text parts.
    """
    tokens = encoding.encode(text)
    parts = []
    text_parts = []
    current_part = []
    current_count = 0

    for token in tokens:
        current_part.append(token)
        current_count += 1

        if current_count >= limit:
            parts.append(current_part)
            current_part = []
            current_count = 0

    if current_part:
        parts.append(current_part)

    # Convert the tokenized parts back to text
    for part in parts:
        text_part = [
            encoding.decode_single_token_bytes(token).decode("utf-8", errors="replace")
            for token in part
        ]
        text_parts.append("".join(text_part))

    return text_parts


def summarize(text: str, instructions: str = "", output_tokens: int = 250) -> str:
    """Summarize a string.

    Args:
        text (str): Text to summarize.
        instructions (str): Additional instructions to append to the prompt.
        output_tokens (int): Maximum number of tokens in the summary.

    Returns:
        str: Text of summary.
    """
    prompt = f"""
        Summarize the text delimited by triple quotes. {instructions}. 
        ```{text}```
        """
    response = openai.Completion.create(
        engine=os.getenv("OPENAI_DEPLOYMENT"),
        prompt=prompt,
        temperature=0.3,
        max_tokens=output_tokens)
    summary = response['choices'][0]['text'].strip()
    return summary


def download_from_azure_storage(blob_path: str, data_path: str, container: str = os.getenv('BLOBSTORAGE_CONTAINER')) -> str:
    """Download a file from Azure Storage.

        Args:
            blob_path (str): Path of blob file relative to the storage container.
            data_path (str): Local path to save file.
            container (str): Storage container.

        Returns:
            str: Local path of saved file.
    """
    blob_service_client = BlobServiceClient.from_connection_string(os.getenv('BLOBSTORAGE_CONNECTION_STRING'))
    blob_client = blob_service_client.get_blob_client(container=container, blob=blob_path)
    with open(data_path, "wb") as download_file:
        try:
            download_file.write(blob_client.download_blob().readall())
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail=f"Document {blob_path} not found "
                                                        f"in container {container}.")
    return data_path
