import requests

response = requests.post(
        # f'https://kobo-connect.azurewebsites.net/kobo',
        # "https://eo55wkfftf6isih.m.pipedream.net",
        "http://127.0.0.1:8000/kobo",
        json={
            "hello": "world!"
        },
        headers={
            'kobotoken': '0',
            'targeturl': "https://eo55wkfftf6isih.m.pipedream.net",
            'targetapikey': '0',
            'hello': 'hola'
        }
    )
print(response, response.content)

# kobotoken = request.headers['kobotoken']
# targeturl = request.headers['targeturl']
# targetapikey = request.headers['targetapikey']