from typing import Tuple, Union, List, Dict

from agilitysync.sync import (
    as_exceptions,
    BaseInbound,
    BaseOutbound,
    BasePayload,
    BaseEvent,
    BaseAttachmentUpload,
    FieldTypes,
    EventTypes,
    EventCategory
)
import re
from datetime import datetime
from dateutil import parser
import time
import json
from external_plugins.gitlab import transformer_functions


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
        event_type = self.event['object_attributes']['action']

        if event_type in ('open'):
            return EventTypes.CREATE
        elif event_type == ('close'):
            return EventTypes.DELETE
        elif event_type in ('update',):
            return EventTypes.UPDATE

        error_msg = 'Unsupported event type [{}]'.format(event_type)
        raise as_exceptions.PayloadError(error_msg)

    def fetch_workitem_id(self):
        return self.event['object_attributes']['id']

    def fetch_workitem_display_id(self):
        return self.event['object_attributes']['iid']

    def fetch_workitem_url(self):
        return "/".join(self.event['object_attributes']['url'].split("/")[1:])

    def fetch_revision(self):
        return self.event['object_attributes']["updated_at"]

    def fetch_timestamp(self):
        timestamp = parser.parse(self.event['object_attributes']["updated_at"])

        return datetime.fromtimestamp(time.mktime(timestamp.utctimetuple())) # type: ignore


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

        event_type = self.event['object_attributes']["action"]

        if event_type in ('open', 'close', 'update'):
            category.append(EventCategory.WORKITEM)
        
        

        ##if self.is_comment_updated(self.event["object_attributes"]["updated_at"], self.event["issue"]["comments_url"]):
            #category.append(EventCategory.COMMENT)

            ##if "Attachment(s):" in self.event['ticket']['latest_comment_html']:
               #category.append(EventCategory.ATTACHMENT)

        return category

    def fetch_parent_id(self):
        parent_id = None
        old_parent_id = None
        _id = transformer_functions.get_parent_id(proj_id =self.event['object_attributes']["project_id"],iid = self.event['object_attributes']["iid"],instance =self.instance_object)
        if _id["epic"] is not None:
            parent_id = _id["epic"]["id"]

        return str(parent_id),old_parent_id

    def normalize_texttype_multivalue_field(self, field_value, field_attr):
        title = []
        multi_select_field_values = [{'field_value': title, 'act': "set"}]
        
        
            
        if len(field_value[0]) != 0:
            
            for value in field_value[0]:
                
                title.append(value['title'])     
                val = {'field_value': title, 'act': "set"}
                multi_select_field_values.append(val)
            return multi_select_field_values
        else:
            return multi_select_field_values

    def migrate_create(self):
        res = transformer_functions.get_issue(self.instance_object,self.project_info,self.workitem_display_id)
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
        event["object_attributes"]["labels"] = labels
        event["object_attributes"]["url"] = res["web_url"]

        return [event]




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
            for outbound_field in transfome_field_objs:
                if outbound_field.is_multivalue:
                     for values in outbound_field.value:
                        multivalues.append(values["field_value"])
                        create_fields[outbound_field.name.lower()] = multivalues
                else:
                    field_name = outbound_field.name
                    field_value = outbound_field.value
                    create_fields[field_name.lower()] = field_value
            parent_val = self.transform_parent_id()
            if parent_val[0] is not None:
                create_fields["epic_id"] = parent_val[0]

            return create_fields
        else:
            create_fields = {}
            multivalues = []
            for outbound_field in transfome_field_objs:
                if outbound_field.is_multivalue:
                    for values in outbound_field.value:
                        multivalues.append(values["field_value"])
                        if values["act"] == "add":
                            create_fields["add_labels"] = multivalues
                        if values["act"] == "remove":
                            create_fields["remove_labels"] = multivalues
                else:
                    field_name = outbound_field.name
                    field_value = outbound_field.value
                    create_fields[field_name.lower()] = field_value
            parent_val = self.transform_parent_id()
            if parent_val[0] is not None:
                create_fields["epic_id"] = parent_val[0]
            return create_fields


    def create(self, sync_fields):
        
        
        try: 
            ticket = transformer_functions.tickets(self.instance_object
                                         ,payload =sync_fields,id =self.project_info["project"],name = self.project_info["display_name"],parentid=self.transform_parent_id())
            orgsplit = self.project_info["project"].split('/')
            org = orgsplit[0]            
            sync_info = {
                "project":  self.project_info["project"],
                "issuetype": "issues",
                "synced_fields": sync_fields
            } 
            xref_object = {
                "relative_url": "{}/{}/{}/{}".format("repos",org,self.project_info["display_name"],"issues"),
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
                                         ,payload=sync_fields,id =self.project_info["project"],name = self.project_info["display_name"],parentid=self.transform_parent_id(),workid = self.workitem_display_id )
        except Exception as e:
            error_msg = ('Unable to sync fields in Gitlab. Error is [{}]. Trying to sync fields \n'
                         '[{} {}]\n.'.format(e, " ", sync_fields))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def comment_create(self, comment):
        try:
            payload = {
                "body": comment            
            }

            ##transformer_functions.tickets(self.instance_object,
                                         ## id=self.workitem_id, payload=payload)
        except Exception as e:
            error_msg = 'Unable to sync comment. Error is [{}]. The comment is [{}]'.format(str(e), comment)
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)
