@router.post("/kobo-to-generic")
async def kobo_to_generic(request: Request):
    """Send a Kobo submission to a generic API.
    API Key is passed as 'x-api-key' in headers."""

    kobo_data = await request.json()
    kobo_data = clean_kobo_data(kobo_data)
    attachments = get_attachment_dict(kobo_data)

    # Create API payload body
    payload = {}
    for kobo_field, target_field in request.headers.items():
        if kobo_field in kobo_data.keys():
            kobo_value = kobo_data[kobo_field].replace(" ", "_")
            if kobo_value not in attachments.keys():
                payload[target_field] = kobo_value
            else:
                file_url = attachments[kobo_value]["url"]
                if "kobotoken" not in request.headers.keys():
                    raise HTTPException(
                        status_code=400,
                        detail=f"'kobotoken' needs to be specified in headers to upload attachments",
                    )
                # encode attachment in base64
                file = get_kobo_attachment(file_url, request.headers["kobotoken"])
                file_b64 = base64.b64encode(file).decode("utf8")
                payload[target_field] = (
                    f"data:{attachments[kobo_value]['mimetype']};base64,{file_b64}"
                )

    # POST to target API
    response = requests.post(
        request.headers["targeturl"],
        headers={"x-api-key": request.headers["targetkey"]},
        data=payload,
    )
    target_response = response.content.decode("utf-8")

    return JSONResponse(status_code=200, content=target_response)