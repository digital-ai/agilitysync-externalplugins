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
from external_plugins.github_plugin import transformer_functions


class Payload(BasePayload):

    def fetch_project(self, event):
        project = str(event["repository"]["id"])
        org = event['organization']['login']
        return project + "/" +org
    def fetch_asset(self, event):
        return "Assettype-001"

    def is_cyclic_event(self, event, sync_user):
        return bool(event['sender']['login'] == str(sync_user))


class Event(BaseEvent):

    def fetch_event_type(self):
        event_type = self.event['action']

        if event_type in ('opened'):
            return EventTypes.CREATE
        elif event_type == ('closed'):
            return EventTypes.DELETE
        elif event_type in ('edited',):
            return EventTypes.UPDATE

        error_msg = 'Unsupported event type [{}]'.format(event_type)
        raise as_exceptions.PayloadError(error_msg)

    def fetch_workitem_id(self):
        return self.event['issue']['id']

    def fetch_workitem_display_id(self):
        return self.event['issue']['id']

    def fetch_workitem_url(self):
        return "/".join(self.event['issue']['url'].split("/")[1:])

    def fetch_revision(self):
        return self.event['issue']["updated_at"]

    def fetch_timestamp(self):
        timestamp = parser.parse(self.event['issue']["updated_at"])

        return datetime.fromtimestamp(time.mktime(timestamp.utctimetuple())) # type: ignore


class Inbound(BaseInbound):
    def connect(self):
        try:
            return transformer_functions.connect(
                                                self.instance_details
            )
        except Exception as e:
            error_msg = 'Connection to Demo plugin failed.  Error is [{}].'.format(str(e))
            raise as_exceptions.InboundError(error_msg, stack_trace=True)

    def is_comment_updated(self, updated_at_with_time, latest_public_comment_html):
        
        
        found_pattern = re.search(updated_at_with_time, latest_public_comment_html)
        if found_pattern:
            return True
        else:
            return False

    def fetch_event_category(self):
        category = []

        event_type = self.event["action"]

        if event_type in ('opened', 'closed', 'edited',):
            category.append(EventCategory.WORKITEM)
        
        

        if self.is_comment_updated(self.event["issue"]["updated_at"], self.event["issue"]["comments_url"]):
            category.append(EventCategory.COMMENT)

            if "Attachment(s):" in self.event['ticket']['latest_comment_html']:
                category.append(EventCategory.ATTACHMENT)

        return category

    def fetch_comment(self):
        comment_data = ""
        if "latest_comment_html" in self.event["ticket"]:
            data = self.event['ticket']['latest_comment_html']
            data = data.replace("----------------------------------------------\n\n", "")
            data = data.split("Attachment(s):\n")
            comment_data = data[0]
        return comment_data


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
        create_fields = {}
        

        for outbound_field in transfome_field_objs:
            create_fields.setdefault(outbound_field.name.lower(),[])
            if outbound_field.is_multivalue:
                for val in outbound_field.value[0]:
                    create_fields[outbound_field.name.lower()].append(val[0])
            else:
                create_fields[outbound_field.name.lower()] =outbound_field.value 
                    
        create_fields["type"] = self.asset_info["asset"]
        return create_fields

    def create(self, sync_fields):

        try: 
            payload = {
                "title": sync_fields['title'],
                "body":" ",
                "assignees": [
                    " "
                ],
                "milestone": 1,
                "labels": [
                    "bug"
                ]
                }

            ticket = transformer_functions.tickets(self.instance_object
                                         ,payload =sync_fields, details=self.instance_details,repo =self.project_info["display_name"],id =self.project_info["project"])
            orgsplit = self.project_info["project"].split('/')
            org = orgsplit[0]
            
            sync_info = {
                "project":  self.project_info["project"],
                "issuetype": "issues",
                "synced_fields": sync_fields
            }
            xref_object = {
                "relative_url": "{}/{}/{}/{}/{}".format("repos",org,self.project_info["display_name"],"issues",ticket["number"]),
                'id': str(ticket["id"]),
                'display_id': str(ticket["id"]),
                'sync_info': sync_info,
            }
            xref_object["absolute_url"] = ticket["repository_url"]
            return xref_object

        except Exception as e:
            error_msg = ("Unable to create [{}] in Github. Error is [{}].\n Trying to sync fields \n"
                         "[{}]\n.".format(self.asset_info["display_name"], e, sync_fields))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def update(self, sync_fields):
        try:
            payload = {
                sync_fields
            }

            transformer_functions.tickets(self.instance_object
                                         ,payload=payload, details=self.instance_details,repo =self.project_info["display_name"],id = self.project_info["id"] ) 

        except Exception as e:
            error_msg = ('Unable to sync fields in Github. Error is [{}]. Trying to sync fields \n'
                         '[{} {}]\n.'.format(e, sync_fields['create_fields'], sync_fields['update_fields']))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def comment_create(self, comment):
        try:
            payload = {
                
                "body": comment
            
            }

            
        except Exception as e:
            error_msg = 'Unable to sync comment. Error is [{}]. The comment is [{}]'.format(str(e), comment)
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)
