# kobo-connect

Connect Kobo to anything.

## Description

Synopsis: a [dockerized](https://www.docker.com/) [python](https://www.python.org/) API that sends Kobo submissions and their attachments to other API-enabled applications, changing field names if necessary. It is basically an extension of the [KoboToolbox REST Services](https://support.kobotoolbox.org/rest_services.html).

Deatils: see [the docs](https://kobo-connect.azurewebsites.net/docs).

## API Usage

### EspoCRM

Using the [`kobo-to-espocrm`](https://kobo-connect.azurewebsites.net/docs#/default/kobo_to_espocrm_kobo_to_espocrm_post) endpoint, it is possible to save a Kobo submission as one or more entities in [EspoCRM](https://www.espocrm.com/). 

Step by step:

1. Define which questions in the Kobo form need to be saved in which entity and field.
2. [Create a new Kobo REST Service](https://support.kobotoolbox.org/rest_services.html).
3. Insert as `Endpoint URL` `https://kobo-connect.azurewebsites.net/kobo-to-espocrm`.
4. For each question, add a `Custom HTTP Header` that specifies to which entity and field it corresponds to.

_Nota bene_:

- The header name (left) must correspond to the Kobo question name (not label).
  - If you have a question of type "Select Many" (select_multiple) in Kobo and you want to save it in a field of type "Multi-Enum" in EspoCRM, add `multi.` before the Kobo question name (see screenshot below). 
- The header value (right) must correspond to the EspoCRM entity name, followed by a dot (`.`), followed by the field name.
- The headers `targeturl` and `targetkey`, corresponding to the EspoCRM URL and API Key respectively, must be included as well.

<img src="https://github.com/rodekruis/kobo-connect/assets/26323051/06de75f3-d02d-4f9f-bb82-db6736542cf5" width="500">


### 121

Using the [`kobo-to-121`](https://kobo-connect.azurewebsites.net/docs#/default/kobo_to_121_kobo_to_121_post) endpoint, it is possible to save a Kobo submission as a Person Affected (PA) registration in the [121 Portal](https://www.121.global/).

Step by step:

1. Define which questions in the Kobo form need to be saved in which field.
2. [Create a new Kobo REST Service](https://support.kobotoolbox.org/rest_services.html).
3. Insert as `Endpoint URL` `https://kobo-connect.azurewebsites.net/kobo-to-121`.
4. For each question, add a `Custom HTTP Header` that specifies to which entity and field it corresponds to.
   - The header name (left) must correspond to the Kobo column name (not label).
   - The header value (right) must correspond to the field name in 121.

_Special Headers_:

- The headers `url121` is required and corresponds the the url of the 121 instance (without trailing `/`, so e.g. https://staging.121.global)
- Headers `username121` and `password121`, corresponding to the 121 username and the 121 password respectively, must be included as well.
- If `programid` is included as a (select one) question, the `XML Value` of the question in kobo needs to be the corresponding number in the 121 portal, the label can be something else, see below
  ![programId](https://github.com/rodekruis/kobo-connect/assets/39266480/1b0ccf53-2740-4432-b31e-d5cb57d2aac5)
- If `programid` is not included as a question, it needs to be added to the header as a number

See below for an example configuration, in which programId was not included as a question so it is included in the header.

<img src="https://github.com/rodekruis/kobo-connect/assets/39266480/bb7b922b-7a39-4093-b525-456687491ba8" width="500">


#### Nota Bene
The 121 API is currently throttled at 3000 submissions per minute. If you expect to go over this limit, please reach out the the 121 platform team.



### Generic endpoint

See [the docs](https://kobo-connect.azurewebsites.net/docs).

## Run locally

```
cp example.env .env
pip install -r requirements.txt
uvicorn main:app --reload
```
