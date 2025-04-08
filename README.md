# kobo-connect

Connect Kobo to anything, including itself.

## Description

Synopsis: a [dockerized](https://www.docker.com/) [python](https://www.python.org/) API that sends Kobo submissions and their attachments to other API-enabled applications, changing field names if necessary. It is basically an extension of the [KoboToolbox REST Services](https://support.kobotoolbox.org/rest_services.html).

Details: see [the docs](https://kobo-connect.azurewebsites.net/docs).

## Linked Kobo form

Using the [`kobo-to-linked-kobo`](https://kobo-connect.azurewebsites.net/docs#/default/kobo_to_linked_kobo_kobo_to_linked_kobo_post) endpoint, it is possible to update a multiple-choice question in a Kobo form (_child_) based on the submissions of another Kobo form (_parent_).

Example: the parent form could be a beneficiary registration form, and the child form could be a follow-up form, or a distribution form. The child form could have a multiple-choice question (`select_one`) with the possible values being the IDs of the beneficiaries registered in the parent form.

> [!TIP]  
> Make sure you understand what you can do with Kobo's [Dynamic Data Attachments](https://support.kobotoolbox.org/dynamic_data_attachment.html). You should use those if e.g. the question in the child form is not a multiple-choice one, or you need to pull specific data from a specific parent submission.

### Setup

1. Define which question in the parent Kobo form needs to be saved in which multiple-choice question in the child form.
2. [Register a new Kobo REST Service](https://support.kobotoolbox.org/rest_services.html) in the parent form and give it a descriptive name, e.g. `update child form`.
3. Insert as `Endpoint URL`:
```
https://kobo-connect.azurewebsites.net/kobo-to-linked-kobo
```
4. Add the following headers under `Custom HTTP Headers`:
   - Under `Name` insert `kobotoken` and under `Value` your Kobo token (see [how to get one](https://support.kobotoolbox.org/api.html#getting-your-api-token)).
   - Under `Name` insert `childasset` and under `Value` the ID of the child form (see [where to find it](https://im.unhcr.org/kobosupport/)).
   - Under `Name` insert `parentasset` and under `Value` the ID of the parent form (see [where to find it](https://im.unhcr.org/kobosupport/)).
   - Under `Name` insert `parentquestion` and under `Value` the name of the question in the parent form (whose answers will determine the choices in the child form).
   - Under `Name` insert `childlist` and under `Value` the name of the _list_ (not question) in the child form. Example: if the question `type` is `select_one list_name`, the value should be `list_name`.

_That's it_. In the child form, you can leave any value(s) under `childlist`, they will be replaced based on the submissions of the parent form. You do NOT need to connect the parent and child form in KoboToolbox. If you want to link another child form to the parent form, repeat steps 2-4 for the other child form.

> [!IMPORTANT]  
> The child form will be redeployed each time a submission is made to the parent form, or the Kobo REST service makes a POST request. If you plan to collect data offline, make sure to enable "form auto-update" in KoboCollect to ensure that the child form is always up-to-date: `settings` > `form management` > `blank form update mode`: `exactly match server`. If, on the other hand, you plan to collect data online via URL, you don't need to do anything, the form be always up to date. 


## EspoCRM

Using the [`kobo-to-espocrm`](https://kobo-connect.azurewebsites.net/docs#/default/kobo_to_espocrm_kobo_to_espocrm_post) endpoint, it is possible to save a Kobo submission as one or more entities in [EspoCRM](https://www.espocrm.com/). 

### Basic setup

1. Define which questions in the Kobo form need to be saved in which entity and field in EspoCRM.
2. In EspoCRM,
   - Create a role (Administration>Roles), set `Access` to the target entity on `enabled`, with the permission on `yes` to `Create` (if you need to update records, also add `Read` and `Edit`).
   - Create an API user (Administration>API Users), give it a descriptive `User Name`, select the previously created role, make sure `Is Active` is checked and that `Authentication Method` is `API Key`. After saving, you will see a newly created API Key which is needed for the next step.
3. [Register a new Kobo REST Service](https://support.kobotoolbox.org/rest_services.html) for the Kobo form of interest and give it a descriptive name.
4. Insert as `Endpoint URL`
```
https://kobo-connect.azurewebsites.net/kobo-to-espocrm
```
6. Add the following headers under `Custom HTTP Headers`:
   - Under `Name` insert `targeturl` and under `Value` the EspoCRM URL (for example, https://espocrminstancex.com).
   - Under `Name` insert `targetkey` and under `Value` the (newly) created API Key (from EspoCRM API User).
9. For each question, add a header that specifies which Kobo questions corresponds to which entity and field EspoCRM: (tip: this is a manual task. If you want to semi-automatically add headers, read this [section](#create-headers-endpoint) on the creating headers endpoint)
   - The header name (left) must correspond to the Kobo question **name**. (You can check the Kobo question name by going into edit mode of the form, open 'Settings' of the specific question and inspect the `Data Column Name`. Also, the Kobo question names can be found in the 'Data' table with previous submissions. This Kobo question name is different from the [Kobo question label](https://support.kobotoolbox.org/getting_started_xlsform.html#adding-questions) and can not contain spaces or symbols (except the underscore).).
   - The header value (right) must correspond to the EspoCRM entity **name**, followed by a dot (`.`), followed by the specific field **name**. Example: `Contact.name`. (EspoCRM name is different from the EspoCRM label, similar to the difference between Kobo question name and Kobo question label).

> [!IMPORTANT]  
> If you need to send **attachments** (e.g. images) to EspoCRM, add a `Custom HTTP Header` called `kobotoken` with your API token (see [how to get one](https://support.kobotoolbox.org/api.html#getting-your-api-token)).

<img src="https://github.com/rodekruis/kobo-connect/assets/26323051/06de75f3-d02d-4f9f-bb82-db6736542cf5" width="500">

### Advanced setup: select many, repeat groups, etc.

- If you have a question of type `Select Many` (`select_multiple`) in Kobo and you want to save it in a field of type `Multi-Enum` in EspoCRM, add `multi.` before the Kobo question name in the header name.
  - Example header: `multi.multiquestion1`: `Entity.field1`
- If you have a **repeating group** of questions in Kobo:
  - you will need to save each repeated question in a different field in EspoCRM, as specified by a different header;
  - under each header name:
    - insert `repeat.`, followed by the repeating group name, followed by a dot (`.`);
    - then insert a number to specify the number of the repeated question (starting from 0), followed by a dot (`.`);
    - then insert the name of the repeated question after the number;
  - under each header value:
    - as before, insert the entity name, followed by a dot (`.`), followed by the field name in EspoCRM.
  - Example headers:
    - `repeat.repeatedgroup.0.repeatedquestion`: `Entity.field1`
    - `repeat.repeatedgroup.1.repeatedquestion`: `Entity.field2`
  - Not all repeated questions need to be filled in nor saved to EspoCRM.
- If you need to **update** a pre-existing record:
  - add a question of type `calculate` called `updaterecordby` in the Kobo form, which will contain the value of the field which you will use to identify the record;
  - add a header with name `updaterecordby` and as value the name of the field that you will use to identify the record.
- If you need to **avoid sending specific submissions** to EspoCRM:
  - add a question called `skipconnect` in the Kobo form;
  - whenever its value is `1` (based on some condition), the submission will not be sent to EspoCRM.
- If you need to **link the new record with another pre-existing record in** EspoCRM:
  - ensure that the API user has read-access to the related entity;
  - under the header name insert the name of the Kobo question, as usual;
  - under the header value insert the entity name, followed by a dot (`.`), followed by the field name of type `Link` (the one containing the related entity record), followed by a dot (`.`), followed by the field name of the related entity used to relate the two.
  - Example headers:
    - `pcode`: `Entity.AdminLevel1.pcode`
    - `programCode`: `Entity.program.code`

## 121

Using the [`kobo-to-121`](https://kobo-connect.azurewebsites.net/docs#/default/kobo_to_121_kobo_to_121_post) endpoint, it is possible to save a Kobo submission as a Person Affected (PA) registration in the [121 Portal](https://www.121.global/).

Step by step:

1. Define which questions in the Kobo form need to be saved in which field.
2. [Create a new Kobo REST Service](https://support.kobotoolbox.org/rest_services.html).
3. Insert as `Endpoint URL` `https://kobo-connect.azurewebsites.net/kobo-to-121`.
4. For each question, add a `Custom HTTP Header` that specifies to which entity and field it corresponds to.
   - The header name (left) must correspond to the Kobo column name (not label).
   - The header value (right) must correspond to the field name in 121.

_Special Headers_:

- The headers `url121` is required and corresponds the url of the 121 instance (without trailing `/`, so e.g. https://staging.121.global)
- Headers `username121` and `password121`, corresponding to the 121 username and the 121 password respectively, must be included as well.
- If `programid` is included as a (select one) question, the `XML Value` of the question in Kobo needs to be the corresponding number in the 121 portal, the label can be something else, see below
  ![programId](https://github.com/rodekruis/kobo-connect/assets/39266480/1b0ccf53-2740-4432-b31e-d5cb57d2aac5)
- If `programid` is not included as a question, it needs to be added to the header as a number

See below for an example configuration, in which programId was not included as a question so it is included in the header.

<img src="https://github.com/rodekruis/kobo-connect/assets/39266480/bb7b922b-7a39-4093-b525-456687491ba8" width="500">


#### Nota Bene
- The 121 API is currently throttled at 3000 submissions per minute. If you expect to go over this limit, please reach out the the 121 platform team.
- If you would like to define which submissions should and should not be send to EspoCRM, you can use the field `skipconnect` in your Kobo form. If the field is set to `1`, the submission will not be send to 121.


## Create headers endpoint
If you need to map a lot of questions, creating the headers manually is cumbersome. The `/create-kobo-headers` endpoint automates this. It expects 4 query parameters:
- `system`: required, enum (options: 121, espocrm, generic)
- `koboassetId`: the asset id of the survey (to be found in the url: https://kobonew.ifrc.org/#/forms/`ASSETID`/summary)
- `kobotoken`: the kobo token of the account the survey is available at (Click on 'account' icon top right > Account Settings > Security > API Key shown is the kobotoken)
- `hookId `: 

In the body you can pass all the headers you want to create as key value pairs, for example:
 ```json
 {
  "last_name": "lastName",
  "first_name": "firstName",
  "household_size": "hhSize"
 }
```
Tip: When you have the headers (/mapping) for example in an Excel table, you can copy that into ChatGPT and ask it to transform the table to key value pairs. It might save time setting up the body needed. The steps for this are the following: 
1. Download the Kobo form in XLS (go to the 'FORM' tab in Kobo -> click the three horizontal dots (settings) -> 'Download XLS'
2. Open the XLS and copy the values from the 'name' column
3. Go to ChatGPT (or other LLM) and prompt the following:
   ````
   Make key value pairs with the following keys and values in JSON output. For every value add "<Your EspoCRM Entity Name>." in front. These are the headers: <paste the values from the 'name' column from the XLS form> 
   ````
4. Copy the output and paste in the ['Request body'](https://kobo-connect.azurewebsites.net/docs#/default/create_kobo_headers_create_kobo_headers_post)
5. Execute the script and confirm that a new REST service in Kobo has been created with the correct headers.


Tip: When you have the headers (/mapping) for example in an Excel table, you can copy that into ChatGPT and ask it to transform the table to key value pairs. It might save time setting up the body needed.

This endpoint assumes the IFRC Kobo server (`https://kobonew.ifrc.org`)

## Generic endpoint

See [the docs](https://kobo-connect.azurewebsites.net/docs).

## Run locally

```
cp example.env .env
pip install -r requirements.txt
uvicorn main:app --reload
```
