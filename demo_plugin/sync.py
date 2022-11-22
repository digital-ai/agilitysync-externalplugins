from bson import ObjectId

from agilitysync.sync import (
    as_exceptions,
    as_log,
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
import external_plugins.zendesk_plugin.zendesk as zendesk


class Payload(BasePayload):

    def fetch_project(self, event):
        return "no_project"

    def fetch_asset(self, event):
        return event['ticket']["type"].lower()

    def is_cyclic_event(self, event, sync_user):
        return bool(event['user']['id'] == str(sync_user))


class Event(BaseEvent):

    def fetch_event_type(self):
        event_type = self.event['action']

        if event_type in ('ticket_created',):
            return EventTypes.CREATE
        elif event_type == 'ticket_deleted':
            return EventTypes.DELETE
        elif event_type in ('ticket_updated', 'comment_created'):
            return EventTypes.UPDATE


        error_msg = 'Unsupported event type [{}]'.format(event_type)
        raise as_exceptions.PayloadError(error_msg)

    def fetch_workitem_id(self):
        return self.event['ticket']['id']

    def fetch_workitem_display_id(self):
        return self.event['ticket']['id']

    def fetch_workitem_url(self):
        return self.event['ticket']['url']

    def fetch_revision(self):
        return self.event['ticket']['updated_at_with_timestamp']

    def fetch_timestamp(self):
        timestamp = parser.parse(self.event['ticket']["updated_at_with_timestamp"])

        return datetime.fromtimestamp(time.mktime(timestamp.utctimetuple()))


class Inbound(BaseInbound):
    def connect(self):
        try:
            return zendesk.Zendesk(self.instance_details['url'], self.instance_details['email'], self.instance_details['password'])
        except Exception as e:
            error_msg = 'Connection to Demo plugin failed.  Error is [{}].'.format(str(e))
            raise as_exceptions.InboundError(error_msg, stack_trace=True)

    def fetch_attachments_metadata(self):
        attachments = []

        for attachment_doc in self.event['issue']['fields'].get('attachment', []):
            attachments.append(
                {
                    "type": "ADDED",
                    "id": attachment_doc["id"],
                    "filename": attachment_doc["filename"],
                    "content_type": attachment_doc['mimeType'],
                    "url": attachment_doc["url"],
                    "headers": {"Authorization": self.instance_object.token}
                }
            )

        return attachments

    def is_comment_updated(self, updated_at_with_time, latest_public_comment_html):
        updated_comment_epoch = datetime.strptime(updated_at_with_time, "%B %d, %Y at %H:%M").timestamp()
        search_pattern = datetime.fromtimestamp(updated_comment_epoch).strftime('%b %d, %Y, %H:%M')
        found_pattern = re.search(search_pattern, latest_public_comment_html)
        if found_pattern:
            return True
        else:
            return False

    def fetch_event_category(self):
        category = []

        event_type = self.event["action"]

        if event_type in ('ticket_created', 'ticket_updated', 'ticket_deleted'):
            category.append(EventCategory.WORKITEM)

        if self.is_comment_updated(self.event["ticket"]["updated_at_with_time"], self.event["ticket"]["latest_public_comment_html"]):
            category.append(EventCategory.COMMENT)

            if "Attachment(s):" in self.event['ticket']['latest_comment_html']:
                category.append(EventCategory.ATTACHMENT)

        # if event_type == 'ticket_created':
        #     if "Attachment(s):" in self.event['ticket']['latest_comment_html']:
        #         category.append(EventCategory.ATTACHMENT)

        # elif event_type == "ticket_updated":
        #     if "Attachment(s):" in self.event['ticket']['latest_comment_html']:
        #         category.append(EventCategory.ATTACHMENT)

        return category

    def fetch_comment(self):
        comment_data = ""
        if "latest_comment_html" in self.event["ticket"]:
            data = self.event['ticket']['latest_comment_html']
            data = data.replace("----------------------------------------------\n\n", "")
            data = data.split("Attachment(s):\n")
            comment_data = data[0]
        return comment_data

    def fetch_parent_id(self):
        parent_id, old_parent_id = (None, None)

        if self.event_type == EventTypes.CREATE:
            for changes in self.event.get('changes', []):
                if changes["super"] is not None:
                    parent_id = changes["super"]

        return (parent_id, old_parent_id)

    def create_remote_link(self, display_id, url, id_field, url_field):
        fields = {}

        if id_field:
            fields[id_field["name"]] = display_id
        if url_field:
            fields[url_field["name"]] = url

        try:
            if fields:
                self.instance_object.update_issue(self.workitem_id, fields, {})
            else:
                self.instance_object.create_remote_link(self.workitem_id, display_id, url)
        except Exception as e:
            as_log.warn('Unable to create remote link. Error is [{}].'.format(str(e)))


class Outbound(BaseOutbound):

    def connect(self):
        try:
            return zendesk.Zendesk(self.instance_details['url'], self.instance_details['email'], self.instance_details['password'])
        except Exception as e:
            error_msg = 'Connection to Demo plugin failed.  Error is [{}].'.format(str(e))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def transform_usertype_value(self, user_value):
        user = self.instance_object.find_user(user_value["username"])
        if user is None:
            err_msg = "Unable to transform user as user does not exists [{}]".format(user_value)
            raise as_exceptions.SkipFieldToSync(err_msg)

    def transform_fields(self, transfome_field_objs):
        create_fields = {}

        for outbound_field in transfome_field_objs:
            field_name = outbound_field.name

            if field_name in ["Assignee"]:  # Temp skip
                continue

            field_value = outbound_field.value
            create_fields[field_name.lower()] = field_value

        create_fields["type"] = self.asset_info["asset"]

        return create_fields

    def create(self, sync_fields):
        try:
            payload = {
                "ticket": sync_fields
            }

            ticket = self.instance_object.tickets(payload=payload)
            sync_info = {
                "project": ticket["external_id"],
                "issuetype": ticket["type"],
                "synced_fields": sync_fields
            }
            xref_object = {
                "relative_url": "/agent/tickets/{}".format(ticket["id"]),
                'id': str(ticket["id"]),
                'display_id': str(ticket["id"]),
                'sync_info': sync_info,
            }
            xref_object["absolute_url"] = "{}{}".format(
                self.instance_details["url"].rstrip("/"),
                xref_object["relative_url"])
            return xref_object

        except Exception as e:
            error_msg = ("Unable to create [{}] in Zendesk. Error is [{}].\n Trying to sync fields \n"
                         "[{}]\n.".format(self.asset_info["display_name"], e, sync_fields))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def create_remote_link(self, inbound_workitem_id, inbound_workitem_url, id_field, url_field):
        try:
            fields = {}
            if id_field:
                fields[id_field['name']] = inbound_workitem_id
            if url_field:
                fields[url_field['name']] = inbound_workitem_url
            if fields:
                self.instance_object.update_issue(self.workitem_id, fields, {})
            else:
                self.instance_object.create_remote_link(self.workitem_id, inbound_workitem_id, inbound_workitem_url)
        except Exception as e:
            as_log.warn('Unable to create remote link in Jira.  Error is [%s].' % (e))

    def update(self, sync_fields):
        try:
            payload = {
                "ticket": sync_fields
            }

            self.instance_object.tickets(id=self.workitem_id, payload=payload)

        except Exception as e:
            error_msg = ('Unable to sync fields in Jira. Error is [{}]. Trying to sync fields \n'
                         '[{} {}]\n.'.format(e, sync_fields['create_fields'], sync_fields['update_fields']))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def comment_create(self, comment):
        try:
            payload = {
                "ticket": {
                    "comment": {
                        "body": comment
                    }
                }
            }

            self.instance_object.tickets(id=self.workitem_id, payload=payload)

            # self.instance_object.issue_add_comment(self.workitem_id, comment)
        except Exception as e:
            error_msg = 'Unable to sync comment. Error is [{}]. The comment is [{}]'.format(str(e), comment)
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def delete(self):
        try:
            self.instance_object.delete_issue(self.instance_object, self.workitem_id)
        except Exception as e:
            error_msg = "Unable to DELETE issue {}. Error is {}.".format(self.workitem_id, str(e))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)


class AttachmentUpload(BaseAttachmentUpload):
    def fetch_header_info(self):
        return {"Authorization": self.instance_object.token}

    def fetch_upload_url(self):
        atch_asset_doc = {
            "Attributes": {
                "Name": {"act": "set", "value": self.filename},
                "ContentType": {"act": "set", "value": self.content_type},
                "Filename": {"act": "set", "value": self.filename},
                "Content": {"act": "set", "value": ""},
                "Asset": {"act": "set", "value": {"idref": self.workitem_id}}
            }
        }
        response = self.instance_object._api_post('Attachment', atch_asset_doc, 'json', 'json')
        self.private_data['response_data'] = response
        return "{}{}".format(self.instance_object.url,
                             re.sub('^\\/[^\\/]+', '', response['Attributes']['Content']['value']))

    def fetch_id(self):
        return self.private_data['response_data']['id']

    def fetch_url(self):
        atch_url = self.private_data['response_data']['Attributes']['Content']['value']
        return "{}{}".format(self.instance_object.url, re.sub('^\\/[^\\/]+', '', atch_url))

    def upload_on_failed(self):
        atch_id = self.private_data['response_data']['id']
        self.instance_object._api_post("Attachment/{}?op=Delete".format(atch_id.split(":")[1]),
                                       {'id': atch_id}, 'json', 'json')

    def remove(self, attachment_id, verify_tls):
        self.instance_object._api_post("Attachment/{}?op=Delete".format(attachment_id.split(":")[1]),
                                       {'id': attachment_id}, 'json', 'json')
