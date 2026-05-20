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
from urllib.parse import quote, parse_qs
from external_plugins.gitlab import transformer_functions
from requests.exceptions import HTTPError
from agilitysync.lib.plugin_manage import plugin_schema
from agilitysync.external_lib.restapi import ASyncRestApi
from bson import ObjectId

class AttachmentUpload(BaseAttachmentUpload):

    def fetch_url(self):
        
         return "{}/{}".format("'https://gitlab.com",self.private_data["url"])

    def fetch_upload_url(self):
        api_url = transformer_functions.get_api_url(self.instance_details["url"])
        return "{}/{}/{}/{}".format(api_url, "projects", self.outbound.project_info["project"], "uploads")
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
        payload = {
            "body": "![{}]({})".format(self.filename, res[0]["url"])
        }
        try:
            transformer_functions.comment(self.instance_object, self.outbound.project_info, payload, self.outbound.workitem_display_id)

        except Exception as e:
            error_msg = 'Unable to sync comment. Error is [{}]. The comment is [{}]'.format(
                str(e), payload.get("body", "")
            )
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def remove(self, attachment_id, verify_tls):
        self.instance_object.post("{}/{}".format(transformer_functions.ATTACHMENT_CREATE_ENDPOINT,
                                                 attachment_id.split(":")[1]),
                                  {'id': attachment_id}, query_str="op=Delete")
class AttachmentDownload(BaseAttachmentDownload):
    def basic_auth(self):
        return None

class Payload(BasePayload):

    def _get_instance_details(self):
        if getattr(self, "_payload_instance_details", None) is None:
            details = plugin_schema.get_plugin_instance_by_id(self.instance_id, self.db)
            if "url" in details:
                details["url"] = details["url"].rstrip("/")
            self._payload_instance_details = details
        return self._payload_instance_details

    def _get_instance_object(self):
        if getattr(self, "_payload_instance_object", None) is None:
            details = self._get_instance_details()
            # Group work-item lookup may run with PAT tokens where PRIVATE-TOKEN auth is required.
            self._payload_instance_object = ASyncRestApi(transformer_functions.get_api_url(details['url']), headers={
                "PRIVATE-TOKEN": "{}".format(details["token"]),
                "Accept": "application/json",
                "Content-Type": "application/json"
            })
        return self._payload_instance_object

    def _group_full_path_from_url(self, event):
        workitem_url = (event.get("object_attributes") or {}).get("url", "")
        # Example: https://gitlab.com/groups/my-group/-/work_items/4
        match = re.search(r"/groups/(?P<group_path>.+?)/-/work_items/", workitem_url)
        return match.group("group_path") if match else None

    def _group_id_from_event(self, event):
        group_path = self._group_full_path_from_url(event)
        if not group_path:
            return None

        # GitLab group paths can contain '/'; API expects URL-encoded full path.
        encoded_group = quote(group_path, safe="")
        try:
            group_info = self._get_instance_object().get("groups/{}".format(encoded_group))
        except Exception:
            # Fallback to plugin's standard connector for environments using bearer-style tokens.
            group_info = transformer_functions.connect(self._get_instance_details()).get("groups/{}".format(encoded_group))
        return str(group_info.get("id")) if group_info and group_info.get("id") is not None else None

    def _handler_name_from_event(self, event):
        if event.get("handler"):
            return event.get("handler")

        headers = event.get("__HEADERS") or {}
        query = headers.get("query") or headers.get("QUERY_STRING") or ""
        if query.startswith("?"):
            query = query[1:]

        handler_name = parse_qs(query).get("handler")
        return handler_name[0] if handler_name else None

    def _project_from_handler_mapping(self, event):
        handler_name = self._handler_name_from_event(event)
        if not handler_name:
            return None

        webhook_doc = self.db.webhookhandlers.find_one({"name": handler_name})
        if not webhook_doc:
            return None

        args = ((webhook_doc.get("directives") or [{}])[0].get("details") or {}).get("args") or {}
        map_names = args.get("map_names") or []
        no_project_candidates = []

        for map_name in map_names:
            try:
                map_doc = self.db.data_map.find_one({"_id": ObjectId(map_name), "active": True})
            except Exception:
                map_doc = None
            if not map_doc:
                continue

            for direction in ("forward-direction", "backward-direction"):
                direction_doc = map_doc.get(direction) or {}
                inbound_doc = direction_doc.get("inbound") or {}
                if inbound_doc.get("instance_id") != self.instance_id:
                    continue

                for system_map in direction_doc.get("system_mapping") or []:
                    project_info = ((system_map.get("inbound_plugin_config") or {}).get("project_info") or {})
                    if project_info.get("id") == "no_project" and project_info.get("project"):
                        no_project_candidates.append(project_info.get("project"))

        # Remove duplicates while preserving order.
        unique_candidates = list(dict.fromkeys(no_project_candidates))

        if len(unique_candidates) == 1:
            return unique_candidates[0]

        if len(unique_candidates) > 1:
            # If handler has multiple no-project mappings, use event group id to disambiguate.
            group_id = self._group_id_from_event(event)
            if group_id:
                for candidate in unique_candidates:
                    if str(candidate).split("/", 1)[0] == str(group_id):
                        return candidate

        return None

    def fetch_project(self, event):
        if event.get("project") and event["project"].get("id") is not None:
            return str(event["project"]["id"])

        # Fallback for older GitLab webhook formats where project_id is at root level
        if event.get("project_id") is not None:
            return str(event["project_id"])

        mapped_project = self._project_from_handler_mapping(event)
        if mapped_project:
            return mapped_project

        group_id = self._group_id_from_event(event)
        if group_id:
            return "{}/No Project".format(group_id)

        raise as_exceptions.PayloadError("Unable to derive project/group id from GitLab payload")

    def fetch_asset(self, event):
        if event.get("object_kind") == "work_item" and (event.get("object_attributes") or {}).get("type") == "Epic":
            return "Assettype-002"
        return "Assettype-001"

    def is_cyclic_event(self, event, sync_user):
        return bool(event['user']['username'] == str(sync_user))


class Event(BaseEvent):

    def fetch_event_type(self):

        if self.event["event_type"] == "note":
            event_type = "update"
        elif self.event['object_attributes']["updated_at"] == self.event['object_attributes']["created_at"]:
            event_type = self.event['object_attributes'].get("action", "open")
        else:
            event_type = self.event['object_attributes'].get("action", "update")

        if event_type == "open":
            return EventTypes.CREATE
        elif event_type == "close":
            return EventTypes.DELETE
        elif event_type == "update":
            return EventTypes.UPDATE

        error_msg = 'Unsupported event type [{}]'.format(event_type)
        raise as_exceptions.PayloadError(error_msg)

    def fetch_workitem_id(self):
        if self.event["event_type"] in ("issue", "work_item"):
            return str(self.event['object_attributes']['id'])
        else:
            return str(self.event['issue']['id'])

    def fetch_workitem_display_id(self):
        if self.event['object_attributes'].get("iid") is not None:
            return self.event['object_attributes']['iid']
        else:
            return self.event['object_attributes']['id']

    def fetch_workitem_url(self):
        return "/".join(self.event['object_attributes']['url'].split("/")[3:])

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
        object_kind = self.event.get("object_kind") or self.event.get("event_type") or ""

        if object_kind == "note":
            note_text = self.event['object_attributes'].get("note") or ""
            if "/uploads/" in note_text:
                category.append(EventCategory.ATTACHMENT)
            else:
                category.append(EventCategory.COMMENT)
        elif object_kind in ("issue", "work_item") or self.event['object_attributes'].get("action") is not None:
            category.append(EventCategory.WORKITEM)
        else:
            category.append(EventCategory.COMMENT)
 
        return category

    def fetch_parent_id(self):
        parent_id = None
        old_parent_id = None
        # project_id may be absent from object_attributes in work_item events;
        # fall back to root-level project_id or project.id
        proj_id = (
            self.event['object_attributes'].get("project_id")
            or self.event.get("project_id")
            or (self.event.get("project") or {}).get("id")
        )
        iid = self.event['object_attributes'].get("iid")
        if not proj_id or not iid:
            return None, old_parent_id
        _id = transformer_functions.get_parent_id(proj_id=proj_id,
                                                  iid=iid,
                                                  instance=self.instance_object)
        if _id and isinstance(_id, dict) and (_id.get("epic") is not None):
            epic_info = _id["epic"]
            group_id = epic_info.get("group_id")
            epic_iid = epic_info.get("iid")
            if group_id and epic_iid:
                try:
                    epic_detail = transformer_functions.get_epic(
                        self.instance_object, {"project": str(group_id)}, epic_iid)
                    parent_id = epic_detail.get("work_item_id")
                except Exception:
                    parent_id = None

        return parent_id, old_parent_id

    def normalize_texttype_multivalue_field(self, field_value, field_attr):
       
        title = []
        multi_select_field_values = [{'field_value': title, 'act': "set"}]
        vals = []
        if len(field_value) == 0:
            raise as_exceptions.SkipFieldToNormalize(
                "Ignoring field because labels are not available.")
        if self.event_type == EventTypes.CREATE:
            if len(field_value[0]) != 0:
                for value in field_value[0]:
                    act = 'add' if value['updated_at'] == value['created_at'] else 'remove'
                    val = {'field_value': value['title'], 'act': act}
                    vals.append(val)
        else:
            
            if len(field_value[0]) != 0:
                for value in field_value[0]:
                    title.append(value["title"])
                val = {'field_value': title, 'act': "set"}
                vals.append(val)
            else:
                return multi_select_field_values


        return vals

    def migrate_create(self):
        is_epic = self.project_info.get("display_name") == "No Project"

        if is_epic:
            res = transformer_functions.get_epic(self.instance_object, self.project_info, self.workitem_display_id)
            event = {"object_attributes": res}
            labels = []
            for label_title in (res.get("labels") or []):
                labels.append({
                    "created_at": res["created_at"],
                    "updated_at": res["updated_at"],
                    "title": label_title,
                })
            event["object_attributes"]["action"] = "open"
            event["object_kind"] = "work_item"
            event["event_type"] = "work_item"
            event["object_attributes"]["type"] = "Epic"
            event["object_attributes"]["created_at"] = res["created_at"]
            event["object_attributes"]["updated_at"] = res["created_at"]
            event["object_attributes"]["labels"] = labels
            event["object_attributes"]["url"] = res.get("web_url") or res.get("url", "")
            return [event]

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
        for val in field_value[0]:
            info = transformer_functions.user_details(self.instance_object, self.project_info)
            if info and val:
                for vals in info:
                    if val == vals["id"]:
                        users.append({"username": vals["name"]})

                if self.event_type == EventTypes.CREATE:
                    for val in users:
                        user_info.append({'field_value': val, 'act': "add"})
                else:
                    user_info.append({'field_value': users, 'act': "set"})
                as_log.info("the users are {}".format(user_info))

            else:
                return []
                
        return user_info

    def normalize_listtype_fieldvalue(self, field_value, field_attr):
        if field_attr['name'] == 'milestone_id':
            name = transformer_functions.get_milestone_name(self.instance_object, self.project_info, field_value)
            return name

        return field_value

    def fetch_comment(self):
        return self.event['object_attributes']["note"]

    def fetch_attachments_metadata(self):
        try:
            note_text = self.event['object_attributes'].get("note") or ""
            # GitLab markdown formats:
            #   image:  ![filename](/uploads/hash/file.ext){optional attrs}
            #   file:   [filename](/uploads/hash/file.ext)
            # Match both — require /uploads/ in path to avoid false positives
            match = re.search(r"!?\[(?P<filename>[^\]]+)\]\((?P<path>/uploads/[^)]+)\)", note_text)
            if not match:
                raise as_exceptions.SkipFieldToNormalize(
                    "Ignoring attachments as there is no attachment")

            filename = match.group("filename")
            raw_path = match.group("path").strip()

            # Build absolute URL.
            # GitLab upload format: {base}/-/project/{project_id}/uploads/{hash}/{file}
            if raw_path.startswith("http://") or raw_path.startswith("https://"):
                full_url = raw_path
            else:
                base_url = str(self.instance_details["url"]).rstrip("/")
                if base_url.endswith("/api/v4"):
                    base_url = base_url[:-7]
                project_id = (self.event.get("project") or {}).get("id", "")
                full_url = "{}/{}/{}".format(
                    base_url,
                    "-/project/{}".format(project_id),
                    raw_path.lstrip("/")
                )

            content_type = raw_path.split(".")[-1].split("{")[0].strip()

            attachment_doc = {
                "id": self.event['object_attributes']['id'],
                "headers": {
                    "PRIVATE-TOKEN": "{}".format(self.instance_details["token"])
                },
                "url": full_url,
                "content_type": content_type,
                "filename": filename,
                "type": "ADDED"
            }
            return [attachment_doc]
        except as_exceptions.SkipFieldToNormalize:
            raise
        except Exception:
            raise as_exceptions.SkipFieldToNormalize(
                "Ignoring attachments as there is no attachment")



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
            users = []
            for outbound_field in transfome_field_objs:
                if outbound_field.is_multivalue:
                    if outbound_field.value:
                        for values in outbound_field.value:
                            if outbound_field.name == "assignee_ids":
                                assigeens = transformer_functions.get_assignee(self.instance_object, self.project_info,
                                                                               self.workitem_display_id)
                                
                                for value in assigeens:
                                    if value == values["id"] and values["act"] == "remove":
                                        continue
                                    
                                    users.append(value)
                                if values["act"] == "add" and values["id"] not in users:
                                    users.append(values["id"])
                                
                                
                                create_fields["assignee_ids"] = users
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
                    # Epics use due_date_fixed/start_date_fixed instead of due_date/start_date.
                    # Always redirect (even when clearing — None clears the fixed date).
                    if is_epic:
                        if field_name.lower() == "due_date":
                            create_fields["due_date_fixed"] = str(field_value).split("T")[0] if field_value else None
                            create_fields["due_date_is_fixed"] = bool(field_value)
                            continue
                        if field_name.lower() == "start_date":
                            create_fields["start_date_fixed"] = str(field_value).split("T")[0] if field_value else None
                            create_fields["start_date_is_fixed"] = bool(field_value)
                            continue
                    # GitLab issues expect YYYY-MM-DD for due_date, strip time if present
                    if field_name.lower() == "due_date" and field_value:
                        field_value = str(field_value).split("T")[0]
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
                                "username"] == vals["name"] :
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
            web_url = ticket.get('web_url') or ''
            # Epics return work_item_id (matches webhook object_attributes.id); issues don't have it.
            xref_id = str(ticket.get('work_item_id') or ticket['id'])
            as_log.info("gitlab/Outbound.create - ticket id=[{}] work_item_id=[{}] using xref_id=[{}]".format(
                ticket.get('id'), ticket.get('work_item_id'), xref_id))
            xref_object = {
                "relative_url": "/".join(web_url.split("/")[3:]) if web_url else web_url,
                'id': xref_id,
                # For epics, GitLab 15.9+ returns work_item_iid alongside iid.
                # Work Items Notes API uses work_item_iid; fall back to iid if not present.
                'display_id': str(ticket.get('work_item_iid') or ticket['iid']),
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

    def delete(self):
        try:
            transformer_functions.delete_issue(
                self.instance_object,
                id=self.project_info["project"],
                name=self.project_info["display_name"],
                workid=self.workitem_display_id
            )
        except Exception as e:
            resp = getattr(self.instance_object, '_response_obj', None)
            status = getattr(resp, 'status_code', None)
            # 204 = deleted successfully (GitLab returns empty body, no JSON to decode)
            # 404 = already deleted; treat as idempotent success
            if status in (204, 404):
                return
            error_msg = 'Unable to delete workitem [{}] in Gitlab. Error is [{}].'.format(
                self.workitem_display_id, str(e))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def create_remote_link(self, workitem_id, url, id_field=None, url_field=None):
        try:
            fields = {}
            if id_field:
                fields[id_field['name']] = str(workitem_id)
            if url_field:
                fields[url_field['name']] = str(url)
            if fields:
                transformer_functions.update_tickets(
                    self.instance_object,
                    payload=fields,
                    id=self.project_info["project"],
                    name=self.project_info["display_name"],
                    parentid=(None, None),
                    workid=self.workitem_display_id
                )
        except Exception as e:
            as_log.warn('gitlab/create_remote_link - Unable to update sync reference field. Error is [{}].'.format(e))

    def comment_create(self, comment):
        try:
            payload = {
                "body": comment
            }
            transformer_functions.comment(self.instance_object,self.project_info,payload,self.workitem_display_id)


        except Exception as e:
            error_msg = 'Unable to sync comment. Error is [{}]. The comment is [{}]'.format(str(e), comment)
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)
