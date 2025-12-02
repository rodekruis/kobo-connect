import requests
import time
from fastapi import Header
import sys
from utils.logger import logger


def required_headers_kobo(kobotoken: str = Header(), koboasset: str = Header()):
    return kobotoken, koboasset


def required_headers_121_kobo(
    url121: str = Header(),
    username121: str = Header(),
    password121: str = Header(),
    kobotoken: str = Header(),
    koboasset: str = Header(),
):
    return url121, username121, password121, kobotoken, koboasset


def get_kobo_attachment(URL, kobo_token):
    """Get attachment from kobo"""
    headers = {"Authorization": f"Token {kobo_token}"}
    timeout = time.time() + 60  # 1 minute from now
    while True:
        data_request = requests.get(URL, headers=headers)
        data = data_request.content
        if sys.getsizeof(data) > 1000 or time.time() > timeout:
            break
        time.sleep(10)
    return data


def get_attachment_dict(kobo_data, kobotoken=None, koboasset=None):
    """Create a dictionary that maps the attachment filenames to their URL."""
    attachments, attachments_list = {}, []
    
    try:
        if kobotoken and koboasset and "_id" in kobo_data.keys():
            time.sleep(30)
            headers = {"Authorization": f"Token {kobotoken}"}
            URL = f"https://kobo.ifrc.org/api/v2/assets/{koboasset}/data/{kobo_data['_id']}/?format=json"
            
            try:
                data_request = requests.get(URL, headers=headers, timeout=30)
                data_request.raise_for_status()
                data = data_request.json()
                
                if "_attachments" in data.keys():
                    attachments_list = data["_attachments"]
                    logger.info(f"Retrieved {len(attachments_list)} attachments from API for submission {kobo_data['_id']}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch attachment data from Kobo API for submission {kobo_data['_id']}: {e}")
                # Fall back to using attachments from kobo_data if available
            except ValueError as e:
                logger.error(f"Failed to parse JSON response from Kobo API: {e}")
        
        if len(attachments_list) == 0:
            if "_attachments" in kobo_data.keys():
                attachments_list = kobo_data["_attachments"]
                logger.info(f"Using {len(attachments_list)} attachments from kobo_data")
            for attachment in attachments_list:
                try:
                    filename = attachment["filename"].split("/")[-1]
                    downloadurl = attachment["download_url"]
                    mimetype = attachment["mimetype"]
                    attachments[filename] = {"url": downloadurl, "mimetype": mimetype}
                except KeyError as e:
                    logger.warning(f"Missing expected key in attachment: {e}. Skipping attachment.")
                    continue
        else:
            for attachment in attachments_list:
                try:
                    filename = attachment["filename"].split("/")[-1]
                    downloadurl = (
                        "https://kc.ifrc.org/media/original?media_file="
                        + attachment["filename"]
                    )
                    mimetype = attachment["mimetype"]
                    attachments[filename] = {"url": downloadurl, "mimetype": mimetype}
                except KeyError as e:
                    logger.warning(f"Missing expected key in attachment: {e}. Skipping attachment.")
                    continue
        
        logger.info(f"Successfully processed {len(attachments)} attachments")
        
    except Exception as e:
        logger.error(f"Unexpected error in get_attachment_dict: {e}")
        return {}
    
    return attachments


def clean_kobo_data(kobo_data):
    """Clean Kobo data by removing group names and converting keys to lowercase."""
    kobo_data_clean = {k.lower(): v for k, v in kobo_data.items()}
    # remove group names
    for key in list(kobo_data_clean.keys()):
        new_key = key.split("/")[-1]
        kobo_data_clean[new_key] = kobo_data_clean.pop(key)
    return kobo_data_clean


def required_headers_linked_kobo(
    kobotoken: str = Header(),
    childasset: str = Header(),
    childlist: str = Header(),
    parentasset: str = Header(),
    parentquestion: str = Header(),
):
    return kobotoken, childasset, childlist, parentasset, parentquestion
