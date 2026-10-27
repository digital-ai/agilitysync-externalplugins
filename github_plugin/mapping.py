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
from common.lib.catocommon import catocommon
from common.lib.rocklogger import logger

class Field(BaseField):
    

    def is_required_field(self):
        if self.field_attr["required"] is True:
            return True
        else:
            return False

    def is_disabled_field(self):
        return False

    def is_custom_field(self):
        return True if "custom_field_options" in self.field_attr or self.field_attr.get("customfield") else False

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
        field_type = self.field_attr["type"]

        if field_type.startswith("projectfield:"):
            return self._fetch_project_fieldtype_info()

        if field_type == "milestone":
            org = self.fields_obj.instance_details["organization"]
            repo = self.fields_obj.project_info["display_name"]
            milestones = transformer_functions.get_field_value(
                self.instance_obj, details=self.instance_details, repo=repo, org=org)
            value_list = [{"id": milestone["id"], "value": milestone["title"], "display_value": milestone["title"]}
                         for milestone in milestones]
            return self._field_type_info(
                FieldTypes.LIST,
                FieldDisplayIcon.DROPDOWN,
                value_list,
                FieldTypes.TEXT
            )

        # title / assignee / labels are all simple text fields.
        return self._field_type_info(FieldTypes.TEXT, FieldDisplayIcon.TEXT)

    def _fetch_project_fieldtype_info(self):
        # GitHub's Projects v2 REST API returns `data_type` as lowercase snake_case
        # (e.g. "single_select", "date", "number"), not camelCase/UPPERCASE.
        data_type = self.field_attr.get("data_type", "text")

        if data_type == "single_select":
            options = self.field_attr.get("options", [])
            value_list = [{"id": option["id"], "value": option["name"]["raw"], "display_value": option["name"]["raw"]}
                         for option in options]
            return self._field_type_info(
                FieldTypes.LIST,
                FieldDisplayIcon.DROPDOWN,
                value_list,
                FieldTypes.TEXT
            )
        elif data_type == "iteration":
            # Iteration field options are unconfirmed against a live delivery; best effort only.
            iterations = self.field_attr.get("iterations", [])
            value_list = [{"id": iteration["id"], "value": iteration.get("title", iteration["id"]),
                          "display_value": iteration.get("title", iteration["id"])} for iteration in iterations]
            return self._field_type_info(
                FieldTypes.LIST,
                FieldDisplayIcon.DROPDOWN,
                value_list,
                FieldTypes.TEXT
            )
        elif data_type == "date":
            return self._field_type_info(FieldTypes.DATE, FieldDisplayIcon.DATE)
        elif data_type == "number":
            return self._field_type_info(FieldTypes.NUMERIC, FieldDisplayIcon.NUMERIC)

        return self._field_type_info(FieldTypes.TEXT, FieldDisplayIcon.TEXT)


class Fields(BaseFields):

    def fetch_fields(self):
        field_list = list(transformer_functions.fields)

        github_project = self.query_params.get("github_project", {})
        if github_project.get("id") not in (None, DEFAULT.NO_PROJECT_ID):
            org = self.instance_details["organization"]
            project_number = github_project["id"]
            for project_field in transformer_functions.get_project_fields(self.instance_obj, org, project_number):
                # Skip built-in/structural fields already covered elsewhere (Title, Assignees, Labels,
                # Milestone, Repository, Type, Reviewers, Parent issue, etc). `data_type` values are
                # lowercase snake_case as returned by GitHub's Projects v2 REST API.
                if project_field.get("data_type") not in ("text", "number", "date", "single_select", "iteration"):
                    continue
                field_list.append({
                    "required": False,
                    "disabled field": False,
                    "customfield": True,
                    "raw_title": "projectfield:{}".format(project_field["id"]),
                    "title": project_field["name"],
                    "type": "projectfield:{}".format(project_field["id"]),
                    "IsMultivalue": False,
                    "data_type": project_field.get("data_type", "text"),
                    "options": project_field.get("options", []),
                    "iterations": project_field.get("configuration", {}).get("iterations", [])
                })

        return field_list


class AssetsManage(BaseAssetsManage):

    def fetch_github_projects(self):
        org = self.instance_details["organization"]

        projects = [
            {
                "id": DEFAULT.NO_PROJECT_ID,
                "display_name": DEFAULT.NO_PROJECT_DISPLAY_NAME
            }
        ]

        for project in transformer_functions.get_projects_v2(self.instance_obj, org):
            projects.append(
                {
                    "id": str(project["number"]),
                    "display_name": project["title"]
                }
            )

        return projects

    def connect(self):
        return transformer_functions.connect(
            self.instance_details
        )
    
    def fetch_sync_user(self):
        user = self.instance_details["Username"]
        return user
    
    def fetch_projects(self):
        org = self.instance_details["organization"]
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
        github_project = self.query_params.get("github_project", {})
        asset_types = [dict(DEFAULT.DEFAULT_ISSUE_TYPE)]

        if github_project.get("id") not in (None, DEFAULT.NO_PROJECT_ID):
            org = self.instance_details["organization"]
            for issue_type in transformer_functions.get_issue_types(self.instance_obj, org):
                asset_types.append(
                    {
                        "id": str(issue_type["id"]),
                        "asset": issue_type["name"],
                        "display_name": issue_type["name"],
                    })

        return asset_types
    
    def test_connection(self):
        try:
            return transformer_functions.check_connection(self.instance_obj,self.instance_details)
        except Exception as ex:
            raise as_exceptions.SanitizedPluginError("Unknown error connecting to GIthub Plugin integration system.", str(ex))

class WebHook(BaseWebHook):

    def create_webhook(self, webhook_name, webhook_url, webhook_description, project_id=None):
        project_info = self.__find_project_info(project_id)
        org = self.instance_details["organization"]
        github_project = self.__fetch_github_project_selection(project_id)

        if github_project.get("id") in (None, DEFAULT.NO_PROJECT_ID):
            self.__create_repo_webhook(org, project_info, webhook_url)
        else:
            self.__create_or_reuse_org_webhook(org, webhook_url)

    def update_webhook(self, webhook_url, project_id=None) -> None:
        project_info = self.__find_project_info(project_id)
        github_project = self.__fetch_github_project_selection(project_id)

        if github_project.get("id") in (None, DEFAULT.NO_PROJECT_ID):
            self.__update_repo_webhook(project_info, webhook_url)
        else:
            self.__update_org_webhook(webhook_url)

    def __find_project_info(self, project_id):
        for project_info in self.projects_info:
            if project_info["id"] == project_id:
                return project_info

        raise ValueError("Unable to find project info for project id [{}]".format(project_id))

    def __fetch_github_project_selection(self, project_id):
        # The base WebHook contract only threads `project_info`/`asset_info` through to this class,
        # so the GitHub Project (v2) selection - a custom asset persisted alongside them - is read
        # back directly from the `fields` collection it was written to during field mapping.
        try:
            db = catocommon.new_mongo_conn()
            doc = db.fields.find_one(
                {
                    "instance_id": self.instance_details["_id"],
                    "plugin_data.config.project_info.id": project_id
                },
                sort=[("_id", -1)]
            )

            if doc:
                for config_entry in doc["plugin_data"]["config"]:
                    if config_entry["project_info"]["id"] == project_id:
                        return config_entry.get("github_project", {})
        except Exception as ex:
            logger.warn("Unable to determine the selected GitHub Project for webhook scope, defaulting to "
                       "repository webhook. The error is [{}].".format(str(ex)))

        return {}

    def __create_repo_webhook(self, org, project_info, webhook_url):
        events = list(DEFAULT.ISSUES_WEBHOOK_EVENTS)
        if self.comments_enabled:
            events.append(DEFAULT.COMMENT_WEBHOOK_EVENT)

        payload = {
            "name": "web",
            "active": True,
            "events": events,
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "insecure_ssl": "0"
            }
        }

        existing_hooks = transformer_functions.webhooks(self.instance_obj, repo=project_info["display_name"],
                                                        id=project_info["project"])
        for hook in existing_hooks:
            if hook.get("config", {}).get("url") == webhook_url:
                return

        transformer_functions.webhooks(self.instance_obj, repo=project_info["display_name"],
                                      id=project_info["project"], payload=payload)

    def __create_or_reuse_org_webhook(self, org, webhook_url):
        existing_hooks = transformer_functions.org_webhooks(self.instance_obj, org)
        for hook in existing_hooks:
            if hook.get("config", {}).get("url") == webhook_url:
                # Already created, either for another repository in this same mapping or by a
                # different mapping sharing the same organization webhook - nothing more to do.
                return

        events = list(DEFAULT.PROJECT_WEBHOOK_EVENTS)
        if self.comments_enabled:
            events.append(DEFAULT.COMMENT_WEBHOOK_EVENT)

        payload = {
            "name": "web",
            "active": True,
            "events": events,
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "insecure_ssl": "0"
            }
        }

        transformer_functions.org_webhooks(self.instance_obj, org, payload=payload)

    def __update_repo_webhook(self, project_info, webhook_url):
        events = list(DEFAULT.ISSUES_WEBHOOK_EVENTS)
        if self.comments_enabled:
            events.append(DEFAULT.COMMENT_WEBHOOK_EVENT)

        org = project_info["project"].split('/')[0]
        existing_hooks = transformer_functions.webhooks(self.instance_obj, repo=project_info["display_name"],
                                                        id=project_info["project"])
        for hook in existing_hooks:
            if hook.get("config", {}).get("url") == webhook_url and set(hook.get("events", [])) != set(events):
                transformer_functions.update_repo_webhook_events(
                    self.instance_obj, org, project_info["display_name"], hook["id"], events)
                return

    def __update_org_webhook(self, webhook_url):
        org = self.instance_details["organization"]
        events = list(DEFAULT.PROJECT_WEBHOOK_EVENTS)
        if self.comments_enabled:
            events.append(DEFAULT.COMMENT_WEBHOOK_EVENT)

        existing_hooks = transformer_functions.org_webhooks(self.instance_obj, org)
        for hook in existing_hooks:
            if hook.get("config", {}).get("url") == webhook_url and set(hook.get("events", [])) != set(events):
                transformer_functions.update_org_webhook_events(self.instance_obj, org, hook["id"], events)
                return

