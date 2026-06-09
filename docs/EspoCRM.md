## EspoCRM

Using the [`kobo-to-espocrm`](https://kobo-connect.azurewebsites.net/docs#/default/kobo_to_espocrm_kobo_to_espocrm_post) endpoint, it is possible to save a Kobo submission as one or more entities in [EspoCRM](https://www.espocrm.com/). 

### Basic setup

1. Define which questions in the Kobo form need to be saved in which entity and field in EspoCRM.
2. In EspoCRM,
   - Create a role (Administration>Roles), set `Access` to the target entity on `enabled`, with the permission on `yes` to `Create` (if you need to update records, also add `Read` and `Edit`).
   - Create an API user (Administration>API Users), give it a descriptive `User Name`, select the previously created role, make sure `Is Active` is checked and that `Authentication Method` is `API Key`. After saving, you will see a newly created API Key which is needed for the next step.
3. [Register a new Kobo REST Service](https://support.kobotoolbox.org/rest_services.html) for the Kobo form of interest and give it a descriptive name.
4. In the Kobo REST service, insert as `Endpoint URL`
```
https://kobo-connect.azurewebsites.net/kobo-to-espocrm
```
5. Add the following headers under `Custom HTTP Headers`:
   - Under header `Name` (left), insert `targeturl` and under `Value` (right) the EspoCRM URL (for example, https://espocrminstancex.com).
   - Under header `Name` (left) insert `targetkey` and under `Value` (right) the (newly) created API Key (from EspoCRM API User).
6. For each question, add a header that specifies which Kobo questions corresponds to which entity and field EspoCRM: (tip: this is a manual task. If you want to semi-automatically add headers, read this [section](#create-headers-endpoint) on the creating headers endpoint)
   - The header `Name` (left) must correspond to the Kobo question **name**. (You can check the Kobo question name by going into edit mode of the form, open 'Settings' of the specific question and inspect the `Data Column Name`. Also, the Kobo question names can be found in the 'Data' table with previous submissions. This Kobo question name is different from the [Kobo question label](https://support.kobotoolbox.org/getting_started_xlsform.html#adding-questions) and can not contain spaces or symbols (except the underscore).).
   - The header `Value` (right) must correspond to the EspoCRM entity **name**, followed by a dot (`.`), followed by the specific field **name**. Example: `Contact.name`. (EspoCRM name is different from the EspoCRM label, similar to the difference between Kobo question name and Kobo question label).

> [!IMPORTANT]  
> If you need to send **attachments** (e.g. images) to EspoCRM, add the following `Custom HTTP Headers`:
> - `kobotoken`: your Kobo API token (see [how to get one](https://support.kobotoolbox.org/api.html#getting-your-api-token)).
> - `koboasset`: your Kobo form asset UID (found in the URL of your form, e.g. `aXXXXXXXXX`).

<img src="https://github.com/rodekruis/kobo-connect/assets/26323051/06de75f3-d02d-4f9f-bb82-db6736542cf5" width="500">

### Advanced setup

#### Select Many

If you have a question of type `Select Many` (`select_multiple`) in Kobo and you want to save it in a field of type `Multi-Enum` in EspoCRM, add `multi.` before the Kobo question name in the header name.

Example header: `multi.multiquestion1`: `Entity.field1`

#### Repeat groups

If you have a **repeating group** of questions in Kobo, you will need to save each repeated question in a different field in EspoCRM, as specified by a different header.

Under each header name:
- insert `repeat.`, followed by the repeating group name, followed by a dot (`.`);
- then insert a number to specify the index of the repetition (starting from 0), followed by a dot (`.`);
- then insert the name of the repeated question.

Under each header value:
- as before, insert the entity name, followed by a dot (`.`), followed by the field name in EspoCRM.

Example headers:
- `repeat.repeatedgroup.0.repeatedquestion`: `Entity.field1`
- `repeat.repeatedgroup.1.repeatedquestion`: `Entity.field2`

Not all repeated questions need to be filled in nor saved to EspoCRM.

#### Update existing records

To update a pre-existing record instead of creating a new one:

1. Add a question of type `calculate` called `updaterecordby` in the Kobo form, which will contain the value of the field you will use to identify the record.
2. Add a header with name `updaterecordby` and as value `Entity.field`, where `Entity` is the EspoCRM entity name and `field` is the field used to identify the record. Example: `Contact.phoneNumber`.

#### Skip specific submissions

To avoid sending specific submissions to EspoCRM:

1. Add a question called `skipconnect` in the Kobo form.
2. Whenever its value is `1` (based on some condition), the submission will not be sent to EspoCRM.

#### Link to related records

To link the new record with another pre-existing record in EspoCRM:

1. Ensure that the API user has read-access to the related entity.
2. Under the header name, insert the name of the Kobo question, as usual.
3. Under the header value, insert the entity name, followed by a dot (`.`), followed by the field name of type `Link` (the one containing the related entity record), followed by a dot (`.`), followed by the field name of the related entity used to look up the matching record. The name of the related entity is inferred from the link field name (e.g., if the link field name is `adminLevel1`, the related entity name is `AdminLevel1` ).

Example headers:
- `pcode`: `Entity.adminLevel1.pcode`
- `programCode`: `Entity.program.programCode`

If the related entity name is different from the link name - shame on you! - you can specify it right after the first entity name, and before the field link name. So under the header value, insert the entity name, followed by a dot (`.`), followed by the related entity name, followed by a dot (`.`), followed by the field name of type `Link` (the one containing the related entity record), followed by a dot (`.`), followed by the field name of the related entity used to look up the matching record.

Example headers:
- `pcode`: `Entity.AdminLevel1.adminLevel1Link.pcode`
- `programCode`: `Entity.Program.programLink.programCode`

#### Datetime values

To send datetime values:

1. Add a [datetime field](https://docs.espocrm.com/administration/fields/#date-time) and a [text field](https://docs.espocrm.com/administration/fields/#text) in EspoCRM. The text field accepts the raw timestamp from Kobo without any validation (e.g. `testinputtext`).
2. Add a header in Kobo to fill the text field. Example: `testinput`: `Entity.testinputtext`.
3. Add an [API Before-Save Script](https://docs.espocrm.com/administration/api-before-save-script/) in the [Entity Manager](https://docs.espocrm.com/administration/entity-manager/#api-before-save-script) to convert the text value into a proper datetime.

Kobo sends datetime values in one of two formats, which require the following formulae:

**Format 1:** `2026-04-23T20:21:06.502+05:30`
```c
if(string\length(testinputtext) > 24) {
  $raw = string\replace(string\substring(testinputtext, 0, 19), 'T', ' ');

  $len  = string\length(testinputtext);
  $sign = string\substring(testinputtext, $len - 6, 1);
  $oh   = string\substring(testinputtext, $len - 5, 2) * 1;
  $om   = string\substring(testinputtext, $len - 2, 2) * 1;
  
  $offset = $oh * 60 + $om;
  if ($sign == '+') { $offset = -$offset; }
  
  testinput = datetime\addMinutes($raw, $offset);
}
```

**Format 2:** `2026-04-27T10:31:14`
```c
if(string\length(testinputtext) > 18) {
  testinput = string\replace(string\substring(testinputtext, 0, 19), 'T', ' ');
}
```

The text field `testinputtext` is a hidden field used to receive the value from Kobo and as input to the datetime calculations. Use the datetime field `testinput` to show the value in EspoCRM.
