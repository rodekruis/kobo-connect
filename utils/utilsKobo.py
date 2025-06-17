import requests
import time
from fastapi import Header
import sys


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
    if kobotoken and koboasset and "_id" in kobo_data.keys():
        time.sleep(30)
        headers = {"Authorization": f"Token {kobotoken}"}
        URL = f"https://kobo.ifrc.org/api/v2/assets/{koboasset}/data/{kobo_data['_id']}/?format=json"
        data_request = requests.get(URL, headers=headers)
        data = data_request.json()
        if "_attachments" in data.keys():
            attachments_list = data["_attachments"]
    if len(attachments_list) == 0:
        if "_attachments" in kobo_data.keys():
            attachments_list = kobo_data["_attachments"]
        for attachment in attachments_list:
            filename = attachment["filename"].split("/")[-1]
            downloadurl = attachment["download_large_url"]
            mimetype = attachment["mimetype"]
            attachments[filename] = {"url": downloadurl, "mimetype": mimetype}
    else:
        for attachment in attachments_list:
            filename = attachment["filename"].split("/")[-1]
            downloadurl = (
                "https://kc.ifrc.org/media/original?media_file="
                + attachment["filename"]
            )
            mimetype = attachment["mimetype"]
            attachments[filename] = {"url": downloadurl, "mimetype": mimetype}
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
