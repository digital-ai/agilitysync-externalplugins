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

from external_plugins.zendesk_plugin import transformer_functions
import external_plugins.zendesk_plugin.default as DEFAULT

from agilitysync.external_lib.restapi import ASyncRestApi

class Field(BaseField):
    def is_required_field(self):
        return self.field_attr["required"]

    def is_disabled_field(self):
        return False

    def is_custom_field(self):
        return True if "custom_field_options" in self.field_attr else False

    def is_readonly_field(self):
        if self.field_attr["type"] == "assignee":
            return self.field_attr["editable_in_portal"]
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
        fields = transformer_functions.ticket_fields(self.instance_obj)
        return fields


class AssetsManage(BaseAssetsManage):

    def connect(self):
        return transformer_functions.connect(
            self.instance_details
        )

    def fetch_sync_user(self):
        user = transformer_functions.get_user_by_email(
            self.instance_obj,
            self.instance_details['email'])
        return user["results"][0]["id"]

    def fetch_projects(self):
        projects = [
            {
                'id': 'no_project',
                'display_name': 'No Projects',
                "project": "no_project"
            }
        ]
        return projects

    def fetch_assets(self):
        asset_types = []
        for field in transformer_functions.ticket_fields(self.instance_obj):
            if field["type"] == "tickettype":
                for option in field["system_field_options"]:
                    asset_types.append(
                        {
                            "id": option["value"],
                            "asset": option["value"],
                            "display_name": option["value"].title(),
                        })
        return asset_types

    def is_instance_supported(self):
        tickets_data = transformer_functions.tickets(self.instance_obj)

        if tickets_data:
            tik_url = tickets_data[0].get("url")
            if (DEFAULT.REST_ENDPOINT_VERSION in tik_url.split("/")):
                return (True, None)
            else:
                return (False, None)
        else:
            return (True, None)

    def test_connection(self):
        try:
            return transformer_functions.check_connection(self.instance_obj)
        except Exception as ex:
            raise as_exceptions.SanitizedPluginError("Unknown error connecting to Zendesk Plugin integration system.", str(ex))


class WebHook(BaseWebHook):

    def create_webhook(self, webhook_name, webhook_url, webhook_description):
        payload = {
            "webhook": {
                "endpoint": "{}".format(webhook_url),
                "http_method": "POST",
                "name": "{}".format(webhook_name),
                "status": "active",
                "request_format": "json",
                "subscriptions": ["conditional_ticket_events"]
            }
        }  # Payload data to create single webhook

        webhook_data = transformer_functions.webhooks(self.instance_obj,
                                                      payload=payload)  # Creating webhook
        category_id = self.create_trigger_categories()  # Creating trigger category
        self.create_triggers(webhook_data["id"], category_id)  # Creating triggers

    def create_trigger_categories(self):
        trigger_category_exist_list = transformer_functions.trigger_categories(self.instance_obj)

        trigger_category_exist = [
            {
                "name": trigger_categories["name"],
                "id": trigger_categories["id"]
            } for trigger_categories in trigger_category_exist_list
            if trigger_categories["name"] == DEFAULT.TRIGGER_CATEGORY_NAME
        ]

        if trigger_category_exist:
            # Trigger category exist return exist category id.
            trigger_categories_id = trigger_category_exist[0]["id"]
            return trigger_categories_id
        else:
            # Trigger category does not exist creating it and return the new category id.
            payload = {
                "trigger_category": {
                    "name": "{}".format(DEFAULT.TRIGGER_CATEGORY_NAME),
                    "position": 0
                }
            }
            catagory_data = transformer_functions.trigger_categories(self.instance_obj,payload=payload)
            return catagory_data["id"]

    def create_triggers(self, webhook_id, category_id):
        """Function to create AgilitySync Triggers.
        """
        self.create_ticket_trigger(webhook_id, category_id)

    def create_ticket_trigger(self, webhook_id, category_id):
        triggers_list = transformer_functions.triggers(self.instance_obj)

        for as_trigger in DEFAULT.AS_TRIGGERS:

            exist_as_trigger = [trigger for trigger in triggers_list
                    if trigger["raw_title"] == as_trigger["title"]]

            if exist_as_trigger:
                update_payload = {
                    "trigger": {
                        "title": "{}".format(as_trigger["title"]),
                        "actions": [{
                            "field": "notification_webhook",
                            "value": ["{}".format(webhook_id), "{\n    \"action\": \"TICKET_ACTION_TYPE\",\n\t\"ticket\": {\n        \"id\": \"{{ticket.id}}\",\n\t\t\"external_id\": \"{{ticket.external_id}}\",\n\t\t\"title\": \"{{ticket.title}}\",\n\t\t\"type\": \"{{ticket.ticket_type}}\",\n\t\t\"status\": \"{{ticket.status}}\",\n\t\t\"url\": \"{{ticket.url}}\",\n        \"description\": \"{{ticket.description}}\",\n\t\t\"created_at_with_timestamp\": \"{{ticket.created_at_with_timestamp}}\",\n\t\t\"created_at_with_time\": \"{{ticket.created_at_with_time}}\",\n\t\t\"updated_at_with_time\": \"{{ticket.updated_at_with_time}}\",\n\t\t\"updated_at_with_timestamp\": \"{{ticket.updated_at_with_timestamp}}\",\n        \"due_date\": \"{{ticket.due_date}}\",\n        \"priority\": \"{{ticket.priority}}\",\n        \"source\": \"{{ticket.via}}\",\n\t\t\"account\": \"{{ticket.account}}\",\n\t\t\"brand_name\": \"{{ticket.brand.name}}\",\n\t\t\"cc_names\": \"{{ticket.cc_names}}\",\n\t\t\"ccs\": \"{{ticket.ccs}}\",\n\t\t\"current_holiday_name\": \"{{ticket.current_holiday_name}}\",\n\t\t\"latest_comment_html\": \"{{ticket.latest_comment_html}}\",\n\t\t\"latest_public_comment_html\": \"{{ticket.latest_public_comment_html}}\",\n\t\t\"tags\": \"{{ticket.tags}}\",\n\t\t\"ticket_field_ID\": \"{{ticket.ticket_field_ID}}\",\n\t\t\"ticket_field_option_title_ID\": \"{{ticket.ticket_field_option_title_ID}}\",\n\t\t\"via\": \"{{ticket.via}}\",\n\t\t\"group\":{\n\t\t\t\"name\": \"{{ticket.group.name}}\"\t\n\t\t},\n\t\t\"requester\": {\n\t\t\t\"details\": \"{{ticket.requester.details}}\",\n\t\t\t\"email\": \"{{ticket.requester.email}}\",\n\t\t\t\"external_id\": \"{{ticket.requester.external_id}}\",\n\t\t\t\"first_name\": \"{{ticket.requester.first_name}}\",\n\t\t\t\"language\": \"{{ticket.requester.language}}\",\n\t\t\t\"last_name\": \"{{ticket.requester.last_name}}\",\n\t\t\t\"name\": \"{{ticket.requester.name}}\",\n\t\t\t\"phone\": \"{{ticket.requester.phone}}\",\n\t\t\t\"requester_field\": \"{{ticket.requester_field}}\"\n\t\t},\n\t\t\"assignee\": {\n            \"email\": \"{{ticket.assignee.email}}\",\n            \"name\": \"{{ticket.assignee.name}}\",\n            \"first_name\": \"{{ticket.assignee.first_name}}\",\n            \"last_name\": \"{{ticket.assignee.last_name}}\"\n    \t},\n\t\t\"organization\": {\n        \t\"name\": \"{{ticket.organization.name}}\",\n\t\t\t\"external_id\": \"{{ticket.organization.external_id}}\",\n\t\t\t\"details\": \"{{ticket.organization.details}}\",\n\t\t\t\"notes\": \"{{ticket.organization.notes}}\"\n   \t\t }\n    },\n    \"user\": {\n        \"external_id\": \"{{current_user.external_id}}\",\n\t\t\"id\": \"{{current_user.id}}\",\n\t\t\"name\": \"{{current_user.name}}\",\n\t\t\"first_name\": \"{{current_user.first_name}}\",\n\t\t\"last_name\": \"{{current_user.last_name}}\",\n\t\t\"email\": \"{{current_user.email}}\",\n\t\t\"details\": \"{{current_user.details}}\",        \n        \"notes\": \"{{current_user.notes}}\",\n        \"phone\": \"{{current_user.phone}}\",\n\t\t\"language\": \"{{current_user.language}}\",\n\t\t\"organization\":{\n\t\t  \"name\": \"{{current_user.organization.name}}\",\n\t\t  \"details\": \"{{current_user.organization.details}}\",\n\t\t  \"notes\": \"{{current_user.organization.notes}}\"\n\t\t}\n    }\n}".replace("TICKET_ACTION_TYPE", as_trigger["webhook_type"])],
                        }],
                        "conditions": exist_as_trigger[0]["conditions"],
                        "category_id": "{}".format(category_id)
                    }
                }
                update_payload["trigger"]["actions"].extend(exist_as_trigger[0]["actions"])
                transformer_functions.triggers(self.instance_obj,
                exist_as_trigger[0]["id"], update_payload)
            else:
                create_payload = {
                    "trigger": {
                        "title": "{}".format(as_trigger["title"]),
                        "actions": [{
                            "field": "notification_webhook",
                            "value": ["{}".format(webhook_id), "{\n    \"action\": \"TICKET_ACTION_TYPE\",\n\t\"ticket\": {\n        \"id\": \"{{ticket.id}}\",\n\t\t\"external_id\": \"{{ticket.external_id}}\",\n\t\t\"title\": \"{{ticket.title}}\",\n\t\t\"type\": \"{{ticket.ticket_type}}\",\n\t\t\"created_at_with_timestamp\": \"{{ticket.created_at_with_timestamp}}\",\n\t\t\"created_at_with_time\": \"{{ticket.created_at_with_time}}\",\n\t\t\"updated_at_with_time\": \"{{ticket.updated_at_with_time}}\",\n\t\t\"updated_at_with_timestamp\": \"{{ticket.updated_at_with_timestamp}}\",\n\t\t\"status\": \"{{ticket.status}}\",\n\t\t\"url\": \"{{ticket.url}}\",\n        \"description\": \"{{ticket.description}}\",\n        \"due_date\": \"{{ticket.due_date}}\",\n        \"priority\": \"{{ticket.priority}}\",\n        \"source\": \"{{ticket.via}}\",\n\t\t\"account\": \"{{ticket.account}}\",\n\t\t\"brand_name\": \"{{ticket.brand.name}}\",\n\t\t\"cc_names\": \"{{ticket.cc_names}}\",\n\t\t\"ccs\": \"{{ticket.ccs}}\",\n\t\t\"current_holiday_name\": \"{{ticket.current_holiday_name}}\",\n\t\t\"latest_comment_html\": \"{{ticket.latest_comment_html}}\",\n\t\t\"latest_public_comment_html\": \"{{ticket.latest_public_comment_html}}\",\n\t\t\"tags\": \"{{ticket.tags}}\",\n\t\t\"ticket_field_ID\": \"{{ticket.ticket_field_ID}}\",\n\t\t\"ticket_field_option_title_ID\": \"{{ticket.ticket_field_option_title_ID}}\",\n\t\t\"via\": \"{{ticket.via}}\",\n\t\t\"group\":{\n\t\t\t\"name\": \"{{ticket.group.name}}\"\t\n\t\t},\n\t\t\"requester\": {\n\t\t\t\"details\": \"{{ticket.requester.details}}\",\n\t\t\t\"email\": \"{{ticket.requester.email}}\",\n\t\t\t\"external_id\": \"{{ticket.requester.external_id}}\",\n\t\t\t\"first_name\": \"{{ticket.requester.first_name}}\",\n\t\t\t\"language\": \"{{ticket.requester.language}}\",\n\t\t\t\"last_name\": \"{{ticket.requester.last_name}}\",\n\t\t\t\"name\": \"{{ticket.requester.name}}\",\n\t\t\t\"phone\": \"{{ticket.requester.phone}}\",\n\t\t\t\"requester_field\": \"{{ticket.requester_field}}\"\n\t\t},\n\t\t\"assignee\": {\n            \"email\": \"{{ticket.assignee.email}}\",\n            \"name\": \"{{ticket.assignee.name}}\",\n            \"first_name\": \"{{ticket.assignee.first_name}}\",\n            \"last_name\": \"{{ticket.assignee.last_name}}\"\n    \t},\n\t\t\"organization\": {\n        \t\"name\": \"{{ticket.organization.name}}\",\n\t\t\t\"external_id\": \"{{ticket.organization.external_id}}\",\n\t\t\t\"details\": \"{{ticket.organization.details}}\",\n\t\t\t\"notes\": \"{{ticket.organization.notes}}\"\n   \t\t }\n    },\n    \"user\": {\n        \"external_id\": \"{{current_user.external_id}}\",\n\t\t\"id\": \"{{current_user.id}}\",\n\t\t\"name\": \"{{current_user.name}}\",\n\t\t\"first_name\": \"{{current_user.first_name}}\",\n\t\t\"last_name\": \"{{current_user.last_name}}\",\n\t\t\"email\": \"{{current_user.email}}\",\n\t\t\"details\": \"{{current_user.details}}\",        \n        \"notes\": \"{{current_user.notes}}\",\n        \"phone\": \"{{current_user.phone}}\",\n\t\t\"language\": \"{{current_user.language}}\",\n\t\t\"organization\":{\n\t\t  \"name\": \"{{current_user.organization.name}}\",\n\t\t  \"details\": \"{{current_user.organization.details}}\",\n\t\t  \"notes\": \"{{current_user.organization.notes}}\"\n\t\t}\n    }\n}".replace("TICKET_ACTION_TYPE", as_trigger["webhook_type"])],
                        }],
                        "conditions": {
                            "any": [{
                                "field": "update_type",
                                "operator": "is",
                                "value": as_trigger["conditions_value"]
                            }]
                        },
                        "category_id": "{}".format(category_id)
                    }
                }

                transformer_functions.triggers(self.instance_obj,
                                               payload=create_payload)
