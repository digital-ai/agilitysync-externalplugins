from typing import Tuple, Union, List, Dict, Optional

from agilitysync.sync import (
    as_exceptions,
    BaseInbound,
    BaseOutbound,
    BasePayload,
    BaseEvent,
    BaseAttachmentUpload,
    BaseAttachmentDownload,
    FieldTypes,
    EventTypes,
    EventCategory,
    as_log
)
import re
from datetime import datetime
from dateutil import parser
import time
import json
from external_plugins.gitlab import transformer_functions
from requests.exceptions import HTTPError

class AttachmentUpload(BaseAttachmentUpload):

    def fetch_url(self):

        return "{}/{}".format("'https://gitlab.com",self.private_data["url"])

    def fetch_upload_url(self):

        return "{}/{}/{}/{}".format(self.instance_details["url"],"projects",self.outbound.project_info["project"],"uploads")
    def fetch_multipart_data(self, storage_obj):
        payload = {
            "file" : storage_obj
        }
        return payload

    def fetch_id(self):
        return self.outbound.workitem_display_id

    def fetch_header_info(self):
        return {"Authorization": "Bearer {}".format(self.instance_details["token"])}

    def upload_on_success(self,response):
        res = []
        res.append(eval(response.text))
        self.private_data = eval(response.text)
        try:
            payload = {
                "body": "![{}]({})".format(self.filename,res[0]["url"])
            }
            transformer_functions.comment(self.instance_object, self.outbound.project_info, payload, self.outbound.workitem_display_id)


        except Exception as e:
            error_msg = 'Unable to sync comment. Error is [{}]. The comment is [{}]'.format(str(e), comment)
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def remove(self, attachment_id, verify_tls):
        self.instance_object.post("{}/{}".format(transformer_functions.ATTACHMENT_CREATE_ENDPOINT,
                                                 attachment_id.split(":")[1]),
                                  {'id': attachment_id}, query_str="op=Delete")
class AttachmentDownload(BaseAttachmentDownload):
    def basic_auth(self):
        return {"rohithamroser","Pwe_96fww3:PF6h"}

class Payload(BasePayload):

    def fetch_project(self, event):
        project = str(event["project"]["id"])
        org = event['project']['namespace']
        return project

    def fetch_asset(self, event):
        return "Assettype-001"

    def is_cyclic_event(self, event, sync_user):
        return bool(event['user']['username'] == str(sync_user))


class Event(BaseEvent):

    def fetch_event_type(self):

        if self.event['object_attributes']["updated_at"] == self.event['object_attributes']["created_at"]:
            event_type = "open"
        if self.event['object_attributes']["updated_at"] != self.event['object_attributes']["created_at"] or self.event["event_type"] == "note" :
            event_type = "update"
        else:
            event_type = self.event['object_attributes']["action"]

        if event_type in ('open'):
            return EventTypes.CREATE
        elif event_type == ('close'):
            return EventTypes.DELETE
        elif event_type in ('update',):
            return EventTypes.UPDATE

        error_msg = 'Unsupported event type [{}]'.format(event_type)
        raise as_exceptions.PayloadError(error_msg)

    def fetch_workitem_id(self):
        if self.event["event_type"] == "issue":
            return str(self.event['object_attributes']['id'])
        else:
            return str(self.event['issue']['id'])

    def fetch_workitem_display_id(self):
        if self.event['object_attributes'].get("iid") is not None:
            return self.event['object_attributes']['iid']
        else:
            return self.event['object_attributes']['id']

    def fetch_workitem_url(self):
        return "/".join(self.event['object_attributes']['url'].split("/")[1:])

    def fetch_revision(self):
        return self.event['object_attributes']["updated_at"]

    def fetch_timestamp(self):
        timestamp = parser.parse(self.event['object_attributes']["updated_at"])

        return datetime.fromtimestamp(time.mktime(timestamp.utctimetuple()))  # type: ignore


class Inbound(BaseInbound):
    def connect(self):
        try:
            return transformer_functions.connect(
                self.instance_details
            )
        except Exception as e:
            error_msg = 'Connection to Gitlab plugin failed.  Error is [{}].'.format(str(e))
            raise as_exceptions.InboundError(error_msg, stack_trace=True)

    def is_comment_updated(self, updated_at_with_time, latest_public_comment_html):

        found_pattern = re.search(updated_at_with_time, latest_public_comment_html)
        if found_pattern:
            return True
        else:
            return False

    def fetch_event_category(self):
        category = []

        if self.event['object_attributes'].get("action") is not None:

            category.append(EventCategory.WORKITEM)
        elif self.event['object_attributes']["note"].find("/upload/"):
            category.append(EventCategory.ATTACHMENT)
        else:
            category.append(EventCategory.COMMENT)


        return category

    def fetch_parent_id(self):
        parent_id = None
        old_parent_id = None
        _id = transformer_functions.get_parent_id(proj_id=self.event['object_attributes']["project_id"],
                                                  iid=self.event['object_attributes']["iid"],
                                                  instance=self.instance_object)
        if _id["epic"] is not None:
            parent_id = _id["epic"]["id"]

        return str(parent_id), old_parent_id

    def normalize_texttype_multivalue_field(self, field_value, field_attr):
        multi_select_field_values = []
        title = []
        if len(field_value) == 0:
            raise as_exceptions.SkipFieldToNormalize(
                "Ignoring field because labels are not available.")
        if self.event_type == EventTypes.CREATE:
            if len(field_value[0]) != 0:
                for value in field_value[0]:
                    act = 'add' if value['updated_at'] == value['created_at'] else 'remove'
                    val = {'field_value': value['title'], 'act': act}
                    multi_select_field_values.append(val)
        else:
            if len(field_value[0]) != 0:
                for value in field_value[0]:
                    title.append(value["title"])
                val = {'field_value': title, 'act': "set"}
                multi_select_field_values.append(val)


        return multi_select_field_values

    def migrate_create(self):
        res = transformer_functions.get_issue(self.instance_object, self.project_info, self.workitem_display_id)
        event = {

            "object_attributes": res,

        }
        labels = []
        if len(res["labels"]) != 0:
            for val in res["labels"]:
                label = {}
                label["created_at"] = res["created_at"]
                label["updated_at"] = res["updated_at"]
                label["title"] = val
                labels.append(label)

        event["object_attributes"]["action"] = "open"
        event["event_type"] = "issue"
        event["object_attributes"]["created_at"] = res["created_at"]
        event["object_attributes"]["updated_at"] = res["created_at"]
        event["object_attributes"]["labels"] = labels
        event["object_attributes"]["url"] = res["web_url"]

        return [event]

    def normalize_usertype_multivalue_field(self, field_value, field_attr):
        user_info = []
        users = []
        if len(field_value) == 0:
            raise as_exceptions.SkipFieldToNormalize(
                "Ignoring field as the username and the email address are not available.")
        for val in field_value:
            info = transformer_functions.user_details(self.instance_object, self.project_info)
            if info and val:
                for vals in info:
                    if val[0] == vals["id"]:
                        users.append({"username": vals["name"]})

                user_info.append({'field_value': users, 'act': "set"})

            else:

                raise as_exceptions.SkipFieldToNormalize(
                    "Ignoring field as the username and the email address are not available.")
        return user_info

    def normalize_listtype_fieldvalue(self, field_value, field_attr):
        if field_attr['name'] == 'milestone_id':
            name = transformer_functions.get_milestone_name(self.instance_object, self.project_info, field_value)
            return name

        return field_value

    def fetch_comment(self):
        return self.event['object_attributes']["note"]

    def fetch_attachments_metadata(self):
        attachment_doc = {
            "id": self.event['object_attributes']['id'],
            "headers": {
                "Authorization": "Bearer {}".format(self.instance_details["token"])
            },
            "url" : re.search("(?P<url>https?://[^\s]+)", self.event["object_attributes"]["description"]).group("url").split(")")[0],
            "content_type" : re.search("(?P<url>https?://[^\s]+)", self.event["object_attributes"]["description"]).group("url") .split(".")[-1].split(")")[0],
            "type" : "ADDED"
        }
        substrings = []
        in_brackets = False
        current_substring = ""

        for c in self.event["object_attributes"]["note"]:
            if c == "[":
                in_brackets = True
            elif c == "]" and in_brackets:
                substrings.append(current_substring)
                current_substring = ""
                in_brackets = False
            elif in_brackets:
                current_substring += c

        if current_substring:
            substrings.append(current_substring)
        attachment_doc["filename"] = substrings[0]
        return [attachment_doc]



class Outbound(BaseOutbound):

    def connect(self):
        try:
            return transformer_functions.connect(
                self.instance_details
            )
        except Exception as e:
            error_msg = 'Connection to Demo plugin failed.  Error is [{}].'.format(str(e))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def transform_fields(self, transfome_field_objs):

        if self.inbound.event_type == EventTypes.CREATE:
            create_fields = {}
            multivalues = []
            multivalues_add = []
            for outbound_field in transfome_field_objs:
                if outbound_field.is_multivalue:
                    if outbound_field.value:
                        if outbound_field.name == "assignee_ids":
                            for vals in outbound_field.value:
                                multivalues_add.append(vals['id'])
                            create_fields["assignee_ids"] = multivalues_add

                        else:
                            for values in outbound_field.value:
                                multivalues.append(values["field_value"])
                                create_fields[outbound_field.name.lower()] = multivalues
                else:

                    if outbound_field.name == "milestone_id":
                        title = transformer_functions.get_milestone_id(self.instance_object, self.project_info,
                                                                       outbound_field.value)
                        field_name = outbound_field.name
                        field_value = title
                    else:
                        field_name = outbound_field.name
                        field_value = outbound_field.value
                    create_fields[field_name.lower()] = field_value
            parent_val = self.transform_parent_id()
            if parent_val[0] is not None:
                create_fields["epic_id"] = parent_val[0]

            return create_fields
        else:
            create_fields = {"issue_type":"issue"}
            multivalues_add = []
            multivalues_rem = []
            for outbound_field in transfome_field_objs:
                if outbound_field.is_multivalue:
                    if outbound_field.value:
                        for values in outbound_field.value:
                            if outbound_field.name == "assignee_ids":
                                assigeens = transformer_functions.get_assignee(self.instance_object, self.project_info,
                                                                               self.workitem_display_id)
                                if values["act"] == "add" and values["id"] not in assigeens:
                                    assigeens.append(values["id"])
                                if assigeens:
                                    if values["act"] == "remove":
                                        assigeens.remove(values["id"])
                                create_fields["assignee_ids"] = assigeens
                            else:
                                if values["act"] == "add":
                                    multivalues_add.append(values["field_value"])
                                    create_fields["add_labels"] = multivalues_add
                                if values["act"] == "remove":
                                    multivalues_rem.append(values["field_value"])
                                    create_fields["remove_labels"] = multivalues_rem
                else:
                    if outbound_field.name == "milestone_id":
                        title = transformer_functions.get_milestone_id(self.instance_object, self.project_info,
                                                                       outbound_field.value)
                        field_name = outbound_field.name
                        field_value = title
                    else:
                        field_name = outbound_field.name
                        field_value = outbound_field.value
                    create_fields[field_name.lower()] = field_value
            parent_val = self.transform_parent_id()
            if parent_val[0] is not None:
                create_fields["epic_id"] = parent_val[0]
            return create_fields

    def transform_usertype_multivalue(self, value, field_obj):
        # To reset multi select user field
        user = value
        user_id = []
        try:
            for no in range(len(user)):
                if 'username' in user[no]["field_value"]:
                    info = transformer_functions.user_details(self.instance_object, self.project_info)
                    if info:
                        for vals in info:
                            if user[no]["field_value"]["username"] == vals["username"] or user[no]["field_value"][
                                "username"] == vals["name"]:
                                user_id.append({"act": user[no]["act"], "id": vals["id"]})

                if not user_id:
                    err_msg = "Unable to transform user [{}] as user does not exist.".format(user)
                    raise as_exceptions.SkipFieldToSync(err_msg)
        except HTTPError as e:
            as_log.error('gitlab/OutboundTransformer - Get user info failed.  Error is [{}].'.format(str(e)))
        except Exception as e:
            as_log.error('gitlab/OutboundTransformer - Get user info failed.  Error is [%s].' % (str(e)))
        finally:
            return user_id

    def create(self, sync_fields):

        try:
            ticket = transformer_functions.tickets(self.instance_object
                                                   , payload=sync_fields, id=self.project_info["project"],
                                                   name=self.project_info["display_name"],
                                                   parentid=self.transform_parent_id())
            orgsplit = self.project_info["project"].split('/')
            org = orgsplit[0]
            sync_info = {
                "project": self.project_info["project"],
                "issuetype": "issues",
                "synced_fields": sync_fields
            }
            xref_object = {
                "relative_url": "{}/{}/{}/{}".format("repos", org, self.project_info["display_name"], "issues"),
                'id': str(ticket['id']),
                'display_id': str(ticket['iid']),
                'sync_info': sync_info,
            }
            xref_object["absolute_url"] = xref_object["relative_url"]
            return xref_object
        except Exception as e:
            error_msg = ("Unable to create [{}] in Gitlab. Error is [{}].\n Trying to sync fields \n"
                         "[{}]\n.".format(self.asset_info["display_name"], e, sync_fields))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def update(self, sync_fields):
        try:

            transformer_functions.update_tickets(self.instance_object
                                                 , payload=sync_fields, id=self.project_info["project"],
                                                 name=self.project_info["display_name"],
                                                 parentid=self.transform_parent_id(), workid=self.workitem_display_id)
        except Exception as e:
            error_msg = ('Unable to sync fields in Gitlab. Error is [{}]. Trying to sync fields \n'
                         '[{} {}]\n.'.format(e, " ", sync_fields))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def comment_create(self, comment):
        try:
            payload = {
                "body": comment
            }
            transformer_functions.comment(self.instance_object,self.project_info,payload,self.workitem_display_id)


        except Exception as e:
            error_msg = 'Unable to sync comment. Error is [{}]. The comment is [{}]'.format(str(e), comment)
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)
