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

import external_plugins.zendesk.zendesk as zendesk

class Field(BaseField):
    def is_required_field(self):
        return self.field_attr["required"]

    def is_disabled_field(self):
        return False

    def is_custom_field(self):
        return True if "custom_field_options" in self.field_attr else False

    def is_readonly_field(self):
        return not self.field_attr["editable_in_portal"]

    def fetch_name(self):
        return self.field_attr["raw_title"]

    def fetch_display_name(self):
        return self.field_attr["title"]

    def is_multivalue_field(self):
        return False  # self.field_attr["IsMultivalue"]

    def fetch_fieldtype_info(self):
        fields_type = {
            "TEXT": "text",
            "TEXTAREA": "textarea",
            "CHECKBOX": "checkbox",
            "DATE": "date",
            "INTEGER": "integer",
            "DECIMAL": "decimal",
            "REGEXP": "regexp",
            "PARTIALCREDITCARD": "partialcreditcard",
            "MULTISELECT": "multiselect",
            "TAGGER": "tagger",
            "LOOKUP": "lookup"
        }

        fields = {
            "subject": {
                "type": fields_type["TEXT"],
                "system": "subject"
            },
            "description": {
                "type": fields_type["TEXT"],
                "system": "description"
            },
            "status": {
                "type": fields_type["TEXT"],
                "system": "status"
            },
            "tickettype": {
                "type": fields_type["TEXT"],
                "system": "tickettype"
            },
            "priority": {
                "type": fields_type["TEXT"],
                "system": "priority"
            },
            "group": {
                "type": fields_type["TEXT"],
                "system": "group"
            },
            "assignee": {
                "type": fields_type["TEXT"],
                "system": "assignee"
            },
            "tagger": {
                "type": fields_type["TEXT"],
                "system": "tagger"
            }
        }
        attribute_type = fields[self.field_attr['type']]["type"].capitalize()

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
        fields = self.instance_obj.fetch_fields().get("ticket_fields")
        return fields

class AssetsManage(BaseAssetsManage):

    def connect(self):
        return zendesk.Zendesk(self.instance_details['url'], self.instance_details['email'], self.instance_details['password'])

    def fetch_sync_user(self):
        user = self.instance_obj.get_user_by_email(self.instance_details['email'])
        return user["users"][0]["id"]

    def fetch_projects(self):
        response = self.instance_obj.fetch_tickets()
        tickets = []

        for ticket in response.get('tickets', []):

            if ("project_parent" in ticket["tags"] or len(ticket["tags"]) == 0):
                tickets.append(
                    {
                        'id': ticket['id'],
                        "project": ticket["id"],
                        'display_name': ticket['subject'],
                    }
                )

        return tickets

    def fetch_assets(self):
        asset_types = []
        project_ids = [proj['id'] for proj in self.query_params["projects"]]

        for asset in self.instance_obj.get_assets(project_ids):
            asset_types.append(
                {
                    "id": asset,
                    "asset": asset,
                    "display_name": asset.title(),
                })

        return asset_types

    def is_instance_supported(self):
        response = self.instance_obj._meta_request('tickets')

        tickets_data = response["tickets"]

        if tickets_data:
            tik_url = tickets_data[0].get("url")
            if (self.instance_obj.rest_endpoint_version in tik_url.split("/")):
                return (True, None)
            else:
                return (False, None)

    def test_connection(self):
        try:
            return self.instance_obj.check_connection()
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
