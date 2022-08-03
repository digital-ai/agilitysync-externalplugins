from agilitysync.mapping import (
    BaseField,
    BaseAssetsManage,
    BaseAutoMap,
    BaseWebHook,
    as_exceptions,
    BaseFields,
    FieldTypes,
    FieldDisplayIcon
)


class Field(BaseField):
    def is_required_field(self):
        return self.field_attr["IsRequired"]

    def is_disabled_field(self):
        return False

    def is_custom_field(self):
        return self.field_attr["IsCustom"]

    def is_readonly_field(self):
        return self.field_attr["IsReadOnly"]

    def fetch_name(self):
        return self.field_attr["Name"]

    def fetch_display_name(self):
        return self.field_attr["Display Name"]

    def is_multivalue_field(self):
        return self.field_attr["IsMultivalue"]

    def fetch_fieldtype_info(self):
        attribute_type = self.field_attr['AttributeType']

        if attribute_type == 'Text':
            return {"type": FieldTypes.TEXT, "display_icon": FieldDisplayIcon.TEXT}
        elif attribute_type == 'LongText':
            return {"type": FieldTypes.HTML, "display_icon": FieldDisplayIcon.HTML}
        elif attribute_type == 'Numeric':
            return {"type": FieldTypes.NUMERIC, "display_icon": FieldDisplayIcon.NUMERIC}
        elif attribute_type == 'Relation':
            return {
                "type": FieldTypes.LIST,
                "display_icon": FieldDisplayIcon.DROPDOWN,
                "values": [
                    {"id": "Status_123", "value": "Status_123", "display_value": "Open"},
                    {"id": "Status_124", "value": "Status_124", "display_value": "In Progress"}
                ],
                "value_type": FieldDisplayIcon.TEXT
            }


class Fields(BaseFields):

    def fetch_fields(self):
        asset_type = self.asset_info["display_name"]

        response = self.instance_obj._meta_request(asset_type)
        return response['Attributes']


class AssetsManage(BaseAssetsManage):

    def connect(self):
        return _connect(self.instance_details['url'], self.instance_details['token'])

    def fetch_sync_user(self):
        response = self.instance_obj._api_get('Member?sel=Username&where=IsSelf=\'True\'', None)
        return response['Assets'][0]['id']

    def fetch_projects(self):
        response = self.instance_obj.api_get('Scope', 'sel=Name,ClosedDate,Parent')
        projects = []

        for project in response.get('Assets', {}):
            projects.append(
                {
                    'id': project['id'],
                    "project": project["id"],
                    'display_name': project['Attributes']['Name']['value'],
                }
            )

        return projects

    def fetch_assets(self):
        asset_types = []

        for asset in self.instance_obj.get_assets(self.instance_obj, [project['id'] for project in self.projects]):
            asset_types.append(
                {
                    "id": asset["id"],
                    "asset": asset["id"],
                    "display_name": asset["name"],
                })

        return asset_types

    def is_instance_supported(self):
        response = self.instance_obj._meta_request('Story')

        return (True, None) if int(response['Version'].split(".")[0]) >= 20 else (False, "20.0")

    def test_connection(self):
        try:
            self.instance_obj.test_connection()
            return "Demo plugin test connection connection is successfull"
        except Exception as ex:
            raise as_exceptions.SanitizedPluginError("Unknown error connecting to Demo Plugin integration system.", str(ex))


class WebHook(BaseWebHook):

    def create_webhook(self, webhook_name, webhook_url, webhook_description):
        self.instance_obj.webhook_post(
            {
                'webhookId': webhook_name,
                'enabled': True,
                'description': webhook_description,
                'url': webhook_url,
            }
        )
