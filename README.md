# kobo-connect

Connect Kobo to anything, including itself.

Built to support Red Cross Red Crescent National Societies.

## Description

Synopsis: a [dockerized](https://www.docker.com/) [python](https://www.python.org/) API that sends Kobo submissions and their attachments to other API-enabled applications, changing field names if necessary. It is basically an extension of the [KoboToolbox REST Services](https://support.kobotoolbox.org/rest_services.html).

Documentation:
* [Kobo](docs/Kobo.md)
* [EspoCRM](docs/EspoCRM.md)
* [121](docs/121.md)
* [Bitrix24](docs/Bitrix24.md)

API Specification: https://kobo-connect.azurewebsites.net/docs

## Run locally

```
pip install poetry
poetry install --no-root
uvicorn main:app --reload
```
