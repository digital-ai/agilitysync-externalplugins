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
from datetime import datetime
from dateutil import parser
import re
import time
import json
from external_plugins.github_plugin import transformer_functions
import external_plugins.github_plugin.default as DEFAULT
from common.lib.rocklogger import logger


class Payload(BasePayload):

    def fetch_project(self, event):
        # `issues` events always carry the owning repository; `projects_v2_item` events are
        # organization-scoped and do not, and since this class has no API connection available to
        # resolve it, those events cannot be routed to a mapping and are skipped (see fetch_asset).
        if "repository" not in event:
            raise as_exceptions.PayloadError(
                "Unable to resolve the repository for a [{}] event.".format(event.get("action", "unknown")))

        org = event["repository"]["owner"]["login"]
        return org + "/" + str(event["repository"]["id"])

    def fetch_asset(self, event):
        # `sub_issues` events carry the issue under `sub_issue` rather than `issue`.
        issue = event.get("issue") or event.get("sub_issue")
        if issue is None:
            raise as_exceptions.PayloadError(
                "Unable to resolve the issue type for a [{}] event.".format(event.get("action", "unknown")))

        issue_type = issue.get("type")
        return issue_type["name"] if issue_type else DEFAULT.DEFAULT_ISSUE_TYPE["asset"]

    def is_cyclic_event(self, event, sync_user):
        return bool(event['sender']['login'] == str(sync_user))


class Event(BaseEvent):

    # 'typed'/'untyped' are deliberately excluded: GitHub fires a separate issues.typed event
    # even when the type is set as part of issue creation, which would otherwise show up as a
    # spurious UPDATE immediately after the CREATE for the same ticket.
    UPDATE_ACTIONS = ('edited', 'field_added', 'field_removed', 'assigned',
                      'unassigned', 'labeled', 'unlabeled', 'milestoned', 'demilestoned')

    # Actions for the issue_comment webhook event (comment deletes/pins are not synced).
    COMMENT_ACTIONS = ('created', 'edited')

    # Actions for the sub_issues webhook event - these only ever change the parent/child link.
    SUB_ISSUE_ACTIONS = ('parent_issue_added', 'parent_issue_removed', 'sub_issue_added', 'sub_issue_removed')

    def fetch_event_type(self):
        event_type = self.event['action']

        if 'sub_issue' in self.event:
            if event_type in self.SUB_ISSUE_ACTIONS:
                return EventTypes.UPDATE
            raise as_exceptions.PayloadError('Unsupported sub_issues event type [{}]'.format(event_type))

        if 'comment' in self.event:
            if event_type in self.COMMENT_ACTIONS:
                return EventTypes.UPDATE
            raise as_exceptions.PayloadError('Unsupported issue_comment event type [{}]'.format(event_type))

        if event_type == 'opened':
            return EventTypes.CREATE
        elif event_type == 'closed':
            return EventTypes.DELETE
        elif event_type in self.UPDATE_ACTIONS:
            return EventTypes.UPDATE

        error_msg = 'Unsupported event type [{}]'.format(event_type)
        raise as_exceptions.PayloadError(error_msg)

    def __fetch_issue(self):
        # sub_issues events reference the changed issue as `sub_issue`; issues/issue_comment
        # events (including comments, which are reported against their parent issue) use `issue`.
        return self.event['sub_issue'] if 'sub_issue' in self.event else self.event['issue']

    def fetch_workitem_id(self):
        return self.__fetch_issue()['id']

    def fetch_workitem_display_id(self):
        return self.__fetch_issue()['id']

    def fetch_workitem_url(self):
        return "/".join(self.__fetch_issue()['url'].split("/")[1:])

    def fetch_revision(self):
        return self.__fetch_issue()["updated_at"]

    def fetch_timestamp(self):
        timestamp = parser.parse(self.__fetch_issue()["updated_at"])

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

    def fetch_event_category(self):
        category = []

        event_type = self.event["action"]

        if 'comment' in self.event:
            category.append(EventCategory.COMMENT)
            return category

        if 'sub_issue' in self.event:
            category.append(EventCategory.WORKITEM)
            return category

        if event_type in ('opened', 'closed') + Event.UPDATE_ACTIONS:
            category.append(EventCategory.WORKITEM)

        return category

    def fetch_comment(self):
        if "comment" in self.event:
            return self.event['comment']['body']
        return ""

    def fetch_parent_id(self):
        if "sub_issue" not in self.event:
            return None, None

        action = self.event["action"]
        if action in ("sub_issue_added", "parent_issue_added"):
            return self.event["parent_issue_id"], None
        elif action in ("sub_issue_removed", "parent_issue_removed"):
            return "", self.event["parent_issue_id"]

        return None, None


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
            # Project v2 custom fields aren't written back to GitHub yet (requires a separate PATCH
            # call against the project item after the issue has been created) - skip them here so
            # they don't get sent as bogus properties on the issue create/update REST call.
            if outbound_field.name.lower().startswith("projectfield:"):
                continue

            create_fields.setdefault(outbound_field.name.lower(),[])
            if outbound_field.is_multivalue:
                for val in outbound_field.value[0]:
                    create_fields[outbound_field.name.lower()].append(val[1])
            else:
                create_fields[outbound_field.name.lower()] =outbound_field.value 
                    
        create_fields["type"] = self.asset_info["asset"]
        return create_fields

    def create(self, sync_fields):

        try:
            ticket = transformer_functions.tickets(self.instance_object
                                         ,payload =sync_fields, details=self.instance_details,repo =self.project_info["display_name"],id =self.project_info["project"])
            orgsplit = self.project_info["project"].split('/')
            org = orgsplit[0]

            self.__add_to_github_project(org, ticket)
            self.__sync_parent_relationship(org, ticket["id"])

            sync_info = {
                "project":  self.project_info["project"],
                "issuetype": "issues",
                "synced_fields": sync_fields
            }
            xref_object = {
                "relative_url": "{}/{}/{}/{}/{}".format("repos",org,self.project_info["display_name"],"issues",ticket["number"]),
                'id': str(ticket["id"]),
                # the issue number (not the global id) is what's directly usable in GitHub's REST
                # paths, and is what the relationship lookup resolves to for a parent issue.
                'display_id': str(ticket["number"]),
                'sync_info': sync_info,
            }
            xref_object["absolute_url"] = ticket["repository_url"]
            return xref_object

        except Exception as e:
            error_msg = ("Unable to create [{}] in Github. Error is [{}].\n Trying to sync fields \n"
                         "[{}]\n.".format(self.asset_info["display_name"], e, sync_fields))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def __add_to_github_project(self, org, ticket):
        # Additive step: when a real GitHub Project (v2) is selected for this mapping, add the
        # newly created issue to it. Project v2 custom field VALUE sync is not implemented yet -
        # only the initial association with the Project is made here.
        github_project = self.assets_info.get("github_project", {})
        if github_project.get("id") in (None, DEFAULT.NO_PROJECT_ID):
            return

        try:
            transformer_functions.add_project_item(
                self.instance_object, org, github_project["id"],
                {"content_id": ticket["id"], "content_type": "Issue"}
            )
        except Exception as ex:
            logger.warn("Unable to add the created issue to GitHub Project [{}]. The error is [{}].".format(
                github_project.get("display_name"), str(ex)))

    def __fetch_issue_number(self):
        # The stored xref id is GitHub's global issue id, which is not usable in the per-repo REST
        # paths below - the issue number is recovered from the stored relative_url
        # (format "repos/{org}/{repo}/issues/{number}") instead.
        workitem_info = self.get_workitem_info()
        if not workitem_info:
            raise as_exceptions.OutboundError(
                "Unable to find the synced GitHub issue for workitem [{}].".format(self.workitem_id))

        return workitem_info["relative_url"].rsplit("/", 1)[-1]

    def __sync_parent_relationship(self, org, child_issue_id):
        # Additive, best-effort step mirroring __add_to_github_project(): GitHub's sub-issues API
        # is called on the parent issue, so the parent's issue number (its display_id) is needed,
        # not its global id - resolved via transform_parent_id()/transform_old_parent_id(), which
        # look up the already-synced parent workitem. Parent and child are assumed to be in the
        # same repo as the current mapping (this plugin only syncs within a single repo per
        # mapping, so cross-repo relationships are not supported).
        if not self.additional_mapping.get("relationship", {}).get("enabled"):
            return

        try:
            repo = self.project_info["display_name"]
            _, old_parent_number = self.transform_old_parent_id()
            _, parent_number = self.transform_parent_id()

            if old_parent_number:
                transformer_functions.remove_sub_issue(self.instance_object, org, repo, old_parent_number, child_issue_id)
            if parent_number:
                transformer_functions.add_sub_issue(self.instance_object, org, repo, parent_number, child_issue_id)
        except Exception as ex:
            logger.warn("Unable to sync parent/sub-issue relationship for issue [{}]. The error is [{}].".format(
                child_issue_id, str(ex)))

    def update(self, sync_fields):
        issue_number = self.__fetch_issue_number()
        org = self.project_info["project"].split('/')[0]

        try:
            transformer_functions.update_ticket(
                self.instance_object, org, self.project_info["display_name"], issue_number, sync_fields)
        except Exception as e:
            error_msg = ('Unable to sync fields in Github. Error is [{}]. Trying to sync fields \n'
                         '[{}]\n.'.format(e, sync_fields))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

        self.__sync_parent_relationship(org, self.workitem_id)

    def comment_create(self, comment):
        issue_number = self.__fetch_issue_number()
        org = self.project_info["project"].split('/')[0]

        try:
            transformer_functions.add_issue_comment(
                self.instance_object, org, self.project_info["display_name"], issue_number, comment)
        except Exception as e:
            error_msg = 'Unable to sync comment. Error is [{}]. The comment is [{}]'.format(str(e), comment)
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def search_before_create(self, search_query):
        # Only called for Data Migration create events. search_query is built from config.json's
        # search_query rules as "field='value'" pairs, AND-joined - GitHub's search API has no OR
        # support across qualifiers, so only simple AND conditions are handled here.
        conditions = [(name, value) for name, value in re.findall(r"(\w+)\s*[=~]\s*'([^']*)'", search_query) if value]
        if not conditions:
            return None

        qualifiers = ' '.join(
            'in:title "{}"'.format(value) if name == "title" else '{}:"{}"'.format(name, value)
            for name, value in conditions)

        org = self.project_info["project"].split('/')[0]
        repo = self.project_info["display_name"]

        try:
            results = transformer_functions.search_issues(self.instance_object, org, repo, qualifiers)
        except Exception as e:
            raise as_exceptions.OutboundError(
                "Unable to search for an existing issue in Github. Error is [{}].".format(e), stack_trace=True)

        items = results.get("items", [])
        if not items:
            return None
        if len(items) > 1:
            raise as_exceptions.OutboundError(
                "Multiple matching Github issues found while searching before create. Query was [{}].".format(
                    qualifiers))

        issue = items[0]
        return {
            "relative_url": "{}/{}/{}/{}/{}".format("repos", org, repo, "issues", issue["number"]),
            "id": str(issue["id"]),
            "display_id": str(issue["number"]),
            "sync_info": {},
            "absolute_url": issue["html_url"],
        }
