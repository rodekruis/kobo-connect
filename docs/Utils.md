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