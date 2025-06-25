## Bitrix24

Using the [`kobo-to-bitrix24`](https://kobo-connect.azurewebsites.net/docs#/Kobo/create_kobo_headers_create_kobo_headers_post) endpoint, it is possible to save a Kobo submission as one or more entities in [Bitrix24](https://www.bitrix24.com/). 

### Basic setup

1. Define which questions in the Kobo form need to be saved in which entity and field in Bitrix24.
2. In Bitrix24, create a new [Webhook](https://helpdesk.bitrix24.com/open/21133100/):
   - From the left menu, select `Developer resources` > `Other` > `Inbound webhook`.
   - Under `Request builder` > `Method`, select `crm.contact.add` (replace `contact` with any other entity you want to save the Kobo submission to).
   - Copy the URL generated below.
   - Click `SAVE`
3. [Register a new Kobo REST Service](https://support.kobotoolbox.org/rest_services.html) for the Kobo form of interest and give it a descriptive name.
4. In the Kobo REST service, insert as `Endpoint URL`
```
https://kobo-connect.azurewebsites.net/kobo-to-bitrix24
```
6. Add the following headers under `Custom HTTP Headers`:
   - Under header `Name` (left), insert `targeturl` and under `Value` (right) the Bitrix24 URL (for example, https://b24-xixckd.bitrix24.com/).
   - Under header `Name` (left) insert `targetkey` and under `Value` (right) the API key in the webhook URL (the one you copied in step 2). The API key is the part after `https://b24-xixckd.bitrix24.com/rest/1/` and before `/crm.contact.add.json`. Example: `1a2b3c4d5e6f7g8h9i0j`.
9. For each question, add a header that specifies which Kobo questions corresponds to which entity and field Bitrix24:
   - The header `Name` (left) must correspond to the Kobo question **name**. You can check the Kobo question name by going into edit mode of the form, open `Settings` of the specific question and inspect the `Data Column Name`. Also, the Kobo question names can be found in the `Data` table with previous submissions. This Kobo question name is different from the [Kobo question label](https://support.kobotoolbox.org/getting_started_xlsform.html#adding-questions) and can not contain spaces or symbols (except the underscore).
   - The header `Value` (right) must correspond to the Bitrix24 method (e.g. `crm.contact.add`) followed by `.json`, followed by the specific field **name**. Example: `crm.contact.add.json:FIELDS[NAME]`. If you don't know the field names if your entity, use a new webhook with method `crm.contact.fields`.

> [!IMPORTANT]  
> Sending **attachments** (e.g. images) to Bitrix24 is currently **not** supported.

<img src="https://github.com/user-attachments/assets/9c8ea559-0d79-41f6-9f47-eeca24c26438" width="500">

