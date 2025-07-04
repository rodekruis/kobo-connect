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

## Create kobo headers
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