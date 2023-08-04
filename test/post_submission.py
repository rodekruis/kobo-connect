import requests

response = requests.post(
        f'http://127.0.0.1:8000/kobo',
        json={
            "hello": "world!"
        }
    )
print(response)