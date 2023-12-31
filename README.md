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
4. Add two `Custom HTTP Headers` called `targeturl` and `targetkey`, with values equal to the EspoCRM URL and API Key, respectively.
5. For each question, add a `Custom HTTP Header` that specifies to which entity and field it corresponds to.

_Nota bene_:

- The header name (left) must correspond to the Kobo question name.
- The header value (right) must correspond to the EspoCRM entity name, followed by a dot (`.`), followed by the field name. Example: `Contact.name`.
- If you have a question of type `Select Many` (`select_multiple`) in Kobo and you want to save it in a field of type `Multi-Enum` in EspoCRM, add `multi.` before the Kobo question name in the header name (see screenshot below). 
- If you need to send **attachments** (e.g. images) to to EspoCRM, add a `Custom HTTP Header` called `kobotoken` with your API token (see [how to get one](https://support.kobotoolbox.org/api.html#getting-your-api-token)).
- If you need to **update** a pre-existing record:
  - add a question of type `calculate` called `updaterecordby` in the kobo form, whcih will contain the value of the field which you will use to identify the record;
  - add a `Custom HTTP Header` called `updaterecordby` with the name of the field that you will use to identify the record.
- The API User in EspoCRM must have a role with `Create` permissions on the target entity; if you need to update records, also `Read` and `Edit`.

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

### Create headers endpoint
If you need to map a lot of questions, creating the headers manually is cumbersome. The `/create-kobo-headers` endpoint automates this. It expects 4 query parameters:
- `system`: required, enum (options: 121, espocrm, generic)
- `kobouser`: your kobo username
- `kobopassword`: your kobo password
- `koboassetId `: the assed id of the survey (to be found in the url: https://kobonew.ifrc.org/#/forms/`ASSETID`/summary)

In the body you can pass all the headers you want to create as key value pairs, for example:
 ```json
 {
  "last_name": "lastName",
  "first_name": "firstName",
  "household_size": "hhSize"
 }
```

This endpoint assumes the IFRC kobo server (`https://kobonew.ifrc.org`)

### Generic endpoint

See [the docs](https://kobo-connect.azurewebsites.net/docs).

## Run locally

```
cp example.env .env
pip install -r requirements.txt
uvicorn main:app --reload
```
