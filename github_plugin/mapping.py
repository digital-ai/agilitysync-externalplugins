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

from external_plugins.github_plugin import transformer_functions
import external_plugins.github_plugin.default as DEFAULT

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
            "RELATION": "Relation"
        }
        fields = {
            "title": {
                "type": fields_type["TEXT"],
                "system": "title"
            }, 
            
            "assignee": {
                "type": fields_type["TEXT"],
                "system": "assignee"
            },
            "labels": {
                "type": fields_type["TEXT"],
                "system": "labels"
            },
            "milestone": {
                "type": fields_type["RELATION"],
                "system": "milestone"
            }
        }
        
        
        
        attribute_type = fields[self.field_attr['type']]['type'].capitalize()

        if attribute_type == "Text":
            return self._field_type_info(FieldTypes.TEXT,  FieldDisplayIcon.TEXT)
        elif attribute_type == "Relation":
            list =transformer_functions.get_field_value(self.instance_obj,details=self.instance_details,repo=self.fields_obj.project_info['display_name'],org = self.fields_obj.project_info['project'] )
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
        fields = transformer_functions.ticfields(self.instance_obj)
        return fields


class AssetsManage(BaseAssetsManage):
    
    def fetch_org(self):
        response_orgs= transformer_functions.get_org(self.instance_obj)
        orgs = []
        for org in response_orgs:
            orgs.append(
                {
                    "id": org["id"],
                    "organization": org["login"],
                    "display_name": org["login"],
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
        org = self.query_params["organization"]["display_name"]
        response_repos= transformer_functions.get_repos(self.instance_obj,org)
        projects = [ ]
        for project in response_repos:
            projects.append(
                {
                    'id': str(project['name']),
                    "project": org + "/" + str(project["id"]),
                    'display_name': project['name'],
                    'parent_id':org
                }
            )
        return projects
    
    def fetch_assets(self):
        org = self.query_params
        asset_types = [org]
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
            return transformer_functions.check_connection(self.instance_obj,self.instance_details)
        except Exception as ex:
            raise as_exceptions.SanitizedPluginError("Unknown error connecting to GIthub Plugin integration system.", str(ex))

class WebHook(BaseWebHook):
    
    def create_webhook(self, webhook_name, webhook_url,webhook_description,project_id):
       
        payload = {

                        "name": "web",
                        "active": True,
                         "events": [
                                        "issues"
                                    ],
                        "config": {
                                        "url": webhook_url,
                                        "content_type": "json",
                                        "insecure_ssl": "0" 
                        }
                        
                }  # Payload data to create single webhook
       
        for project in self.projects_info:
            transformer_functions.webhooks(self.instance_obj,repo = project['display_name'],id = project['project']
                                                      ,payload=payload)  
