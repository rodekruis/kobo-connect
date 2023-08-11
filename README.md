# kobo-connect

Connect Kobo to anything.

## Description

Synopsis: a [dockerized](https://www.docker.com/) [python](https://www.python.org/) API that sends Kobo submissions and their attachments to other API-enabled applications, changing field names if necessary. It is basically an extension of the [KoboToolbox REST Services](https://support.kobotoolbox.org/rest_services.html).

Deatils: see [the docs](https://kobo-connect.azurewebsites.net/docs).

## API Usage

#### EspoCRM

Using the [`kobo-to-espocrm`](https://kobo-connect.azurewebsites.net/docs#/default/kobo_to_espocrm_kobo_to_espocrm_post) endpoint, it is possible to save a Kobo submission as one or more entities in [EspoCRM](https://www.espocrm.com/). Step by step:
1. Define which questions in the Kobo form need to be saved in which entity and field.
2. [Create a new Kobo REST Service](https://support.kobotoolbox.org/rest_services.html).
3. Insert as `Endpoint URL` `https://kobo-connect.azurewebsites.net/kobo-to-espocrm`.
4. For each question, add a `Custom HTTP Header` that specifies to which entity and field it corresponds to.

 _Nota bene_:
* The header name must correspond to the Kobo column name (not label).
* The header value must correspond to the EspoCRM entity name, followed by a dot (`.`), followed by the field name.
* The headers `targeturl` and `targetkey`, corresponding to the EspoCRM URL and API Key respectively, must be included as well.

<img src="https://github.com/jmargutt/kobo-connect/assets/26323051/62c1471f-80c4-4f13-b202-125c8aa5c7b8" width="500">


#### 121
TBI

#### Generic endpoint
TBI

See [the docs](https://kobo-connect.azurewebsites.net/docs).

## Run locally
```
pip install -r requirements.txt
uvicorn main:app --reload
```
