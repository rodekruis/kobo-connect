def clean_text(text):
    # Normalize text to remove accents
    normalized_text = unicodedata.normalize("NFD", text)
    # Remove accents and convert to lowercase
    cleaned_text = "".join(
        c for c in normalized_text if not unicodedata.combining(c)
    ).lower()
    return cleaned_text


def required_headers_121(
    url121: str = Header(), username121: str = Header(), password121: str = Header()
):
    return url121, username121, password121

# Dictionary to store cookies, credentials, and expiration times
cookie121 = {}

def login121(url121, username, password):
    # Check if URL exists in the dictionary
    if url121 in cookie121:
        cookie_data = cookie121[url121]
        # Check if the stored username and password match
        if cookie_data['username'] == username and cookie_data['password'] == password:
            cookie_expiry = cookie_data['expiry']
            current_time = datetime.utcnow()

            # Check if the cookie is valid for at least 24 more hours
            if (cookie_expiry - current_time) >= timedelta(hours=24):
                logger.info(f"Using cached cookie for {url121}")
                return cookie_data['cookie']
            else:
                logger.info(f"Cookie for {url121} is valid for less than 24 hours, refreshing cookie...")

    # Otherwise, request a new cookie
    body = {'username': username, 'password': password}
    url = f'{url121}/api/users/login'
    
    try:
        login_response = requests.post(url, data=body)
        login_response.raise_for_status()
    except requests.RequestException as e:
        error_message = str(e)
        logger.error(
            f"Failed: 121 login returned {login_response.status_code} {error_message}",
            extra=None,
        )
        raise HTTPException(
            status_code=login_response.status_code, detail=error_message
        )
    
    # Parse the response
    response_data = login_response.json()
    cookie = response_data['access_token_general']

    # Store the new cookie, username, password, and expiration time in the dictionary
    expiry_datetime = datetime.fromisoformat(response_data['expires'].replace("Z", ""))
    
    cookie121[url121] = {
        'username': username,
        'password': password,
        'cookie': cookie,
        'expiry': expiry_datetime
    }
    
    logger.info(f"New cookie stored for {url121} with credentials.")
    return cookie
