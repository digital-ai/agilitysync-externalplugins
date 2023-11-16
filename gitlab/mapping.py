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

from external_plugins.gitlab import transformer_functions
import external_plugins.gitlab.default as DEFAULT

from agilitysync.external_lib.restapi import ASyncRestApi


class Field(BaseField):

    def is_required_field(self):
        if self.field_attr["required"] is True:
            return True
        else:
            return False

    def is_disabled_field(self):
        return False

    def is_custom_field(self):
        return True if "custom_field_options" in self.field_attr else False

    def is_readonly_field(self):
        return False

    def fetch_name(self):
        return self.field_attr["raw_title"]

    def fetch_display_name(self):
        return self.field_attr["title"]

    def is_multivalue_field(self):
        if self.field_attr["IsMultivalue"]:
            return True
        else:
            return False

    def _field_type_info(self, field_type, display_image, values=None, value_type=None):
        field_type_doc = {"type": field_type}

        if values is not None and value_type is not None:
            field_type_doc["value_type"] = value_type
            field_type_doc["values"] = values

        if display_image:
            field_type_doc["display_icon"] = display_image

        return field_type_doc

    def get_field_value(self, field_type, id, asset):
        if field_type == "color":
            colors = ["Red", "Blue", "Green", "Orange", "Purple"]
            return colors
        else:
            list = transformer_functions.get_fields_values(self.instance_obj, field_type)

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
            "LOOKUP": "lookup",
            "RELATION": "Relation",
            "BOOLEAN": "Boolean"
        }
        fields = {
            "title": {
                "type": fields_type["TEXT"],
                "system": "title"
            },
            "labels": {
                "type": fields_type["TEXT"],
                "system": "labels"
            },
            # "color": {
            #     "type": fields_type["RELATION"],
            #     "system": "color"
            # },
            "weight": {
                "type": fields_type["INTEGER"],
                "system": "weight"
            },
            "description": {
                "type": fields_type["TEXT"],
                "system": "description"
            },
            "confidential": {
                "type": fields_type["BOOLEAN"],
                "system": "confidential"
            },
            "start_date_fixed": {
                "type": fields_type["DATE"],
                "system": "start_date_fixed"
            },
            "due_date_fixed": {
                "type": fields_type["DATE"],
                "system": "due_date_fixed"
            }

        }
        attribute_type = fields[self.field_attr['type']]['type'].capitalize()

        if attribute_type == 'Text':
            return self._field_type_info(FieldTypes.TEXT, FieldDisplayIcon.TEXT)
        if attribute_type == 'Integer':
            return self._field_type_info(FieldTypes.NUMERIC, FieldDisplayIcon.NUMERIC)
        if attribute_type == 'Date':
            return self._field_type_info(FieldTypes.DATETIME, FieldDisplayIcon.DATETIME)
        if attribute_type == 'Boolean':
            return self._field_type_info(FieldTypes.BOOLEAN_LIST, FieldDisplayIcon.BOOLEAN,
                                         transformer_functions.BOOLEAN_VALUES, FieldTypes.BOOLEAN)
        elif attribute_type == 'Relation':
            list = transformer_functions.get_field_value(self.instance_obj, details=self.instance_details,
                                                         repo=self.fields_obj.project_info['display_name'],
                                                         org=self.fields_obj.query_params["organization"][
                                                             'display_name'])
            value_list = []
            for values in list:
                value_list.append({"id": values["id"], "value": values["title"], "display_value": values["title"]})
            return self._field_type_info(
                FieldTypes.LIST,
                FieldDisplayIcon.DROPDOWN,
                value_list,
                FieldTypes.TEXT
            )


class Fields(BaseFields):

    def fetch_fields(self):

        if self.asset_info["display_name"] == "epic":
            fields = transformer_functions.epicfields()

        else:
            fields = transformer_functions.ticfields()
        return fields


class AssetsManage(BaseAssetsManage):

    def fetch_org(self):
        response_orgs = transformer_functions.get_org(self.instance_obj)
        orgs = []
        for org in response_orgs:
            orgs.append(
                {
                    'id': org['id'],
                    "organization": org["name"],
                    'display_name': org['name'],

                }
            )
        return orgs

    def connect(self):
        return transformer_functions.connect(
            self.instance_details
        )

    def fetch_sync_user(self):
        user = self.instance_details["Username"]
        return user

    def fetch_projects(self):
        org = self.query_params["organization"]["id"]
        response_repos = transformer_functions.get_repos(self.instance_obj, org)
        projects = []
        for project in response_repos:
            projects.append(
                {
                    'id': str(project['name']),
                    "project": str(project["id"]),
                    'display_name': project['name'],

                }
            )
        projects.append(
            {'id': "no_project", "project": str(self.query_params["organization"]["id"]) + "/" + "No Project",
             "display_name": "No Project"})
        return projects

    def fetch_assets(self):

        asset_types = []
        proj = self.query_params["projects"][0]
        if proj["id"] == "no_project":
            asset_types.append(
                {
                    "id": "Assettype-002",
                    "asset": "Assettype-002",
                    "display_name": "epic",
                })
        else:
            for field in transformer_functions.ticket_fields(self.instance_obj):
                asset_types.append(
                    {
                        "id": field["id"],
                        "asset": field["id"],
                        "display_name": field["display_name"],
                    })
        return asset_types

    def test_connection(self):
        try:
            return transformer_functions.check_connection(self.instance_obj, self.instance_details)
        except Exception as ex:
            raise as_exceptions.SanitizedPluginError("Unknown error connecting to GItlab Plugin integration system.",
                                                     str(ex))


class WebHook(BaseWebHook):

    def create_webhook(self, webhook_name, webhook_url, webhook_description, project_id):
        payload = {

            "url": webhook_url,
            "issues_events": True

        }  # Payload data to create single webhook

        for project in self.projects_info:
            transformer_functions.webhooks(self.instance_obj, id=project['project']
                                           , payload=payload)
