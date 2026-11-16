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
from agilitysync.lib.plugin_manage import plugin_info
from datetime import datetime
from dateutil import parser
import itertools
import re
import time
import json
from urllib.parse import urlparse
from external_plugins.github_plugin import transformer_functions
import external_plugins.github_plugin.default as DEFAULT


def _broaden_asset_match(node, asset, default_asset):
    # Walks the Mongo query produced by BasePayload.fetch_query, replacing exact-match conditions
    # on "...asset_info.asset" == asset with an $in on [asset, default_asset] in place, so a
    # No-Project mapping (which only ever offers the synthetic default asset) still matches.
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key.endswith("asset_info.asset") and value == asset:
                node[key] = {"$in": [asset, default_asset]}
            elif (key == "$eq" and isinstance(value, list) and len(value) == 2 and
                  isinstance(value[0], str) and value[0].endswith("asset_info.asset") and value[1] == asset):
                del node["$eq"]
                node["$in"] = [value[0], [asset, default_asset]]
            else:
                _broaden_asset_match(value, asset, default_asset)
    elif isinstance(node, list):
        for item in node:
            _broaden_asset_match(item, asset, default_asset)


def _write_sync_reference(instance, org, repo, issue_number, display_id, url, id_field, url_field, project_number):
    try:
        if not id_field and not url_field:
            # Like Agility's Link fallback when no sync reference field is chosen.
            transformer_functions.add_issue_comment(
                instance, org, repo, issue_number, "Synced with Digital.ai Agility [{}]({})".format(display_id, url))
            return

        issue_values, project_values = [], []
        for field, value in ((id_field, display_id), (url_field, url)):
            name = (field or {}).get("name", "")
            if not value:
                continue
            if name.startswith(DEFAULT.ISSUE_FIELD_PREFIX):
                issue_values.append({"field_id": int(name[len(DEFAULT.ISSUE_FIELD_PREFIX):]), "value": str(value)})
            elif name.startswith(DEFAULT.PROJECT_FIELD_PREFIX):
                project_values.append({"id": int(name[len(DEFAULT.PROJECT_FIELD_PREFIX):]), "value": str(value)})

        if issue_values:
            transformer_functions.add_issue_field_values(instance, org, repo, issue_number, issue_values)

        if project_values:
            item_id = transformer_functions.find_issue_project_item_id(instance, org, repo, issue_number, project_number)
            if item_id is None:
                raise Exception("the issue is not in GitHub Project [{}]".format(project_number))
            transformer_functions.update_project_item(instance, org, project_number, item_id, {"fields": project_values})
    except Exception as ex:
        as_log.warn("Unable to set sync reference on GitHub issue [{}/{}#{}]. The error is [{}].".format(
            org, repo, issue_number, str(ex)))


def _project_field_value(value):
    # single_select arrives as {"name": ...} and iteration as {"title": ...}; other types are plain.
    if isinstance(value, dict):
        return _raw_text(value.get("name") or value.get("title")) or ""
    return "" if value is None else value


def _raw_text(value):
    # Projects REST returns some names/titles as {"raw": ..., "html": ...}.
    return value.get("raw") if isinstance(value, dict) else value


def _project_field_api_value(field, value):
    # Shape expected by PATCH .../projectsV2/{n}/items/{id}; None clears the field.
    if value in (None, "", []):
        return None

    data_type = field.get("data_type")
    if data_type == "single_select":
        options = field.get("options") or []
    elif data_type == "iteration":
        options = (field.get("configuration") or {}).get("iterations") or []
    elif data_type == "number":
        return float(value)
    elif data_type == "date":
        return str(value)[:10]
    else:
        return str(value)

    for option in options:
        if _raw_text(option.get("name") or option.get("title")) == value:
            return option["id"]
    raise ValueError("Value [{}] is not an option of GitHub Project field [{}].".format(value, field.get("name")))


class Payload(BasePayload):

    def fetch_events(self):
        if "projects_v2_item" not in self.payload:
            return [self.payload]

        event = self.__fetch_project_item_event()
        return [event] if event else []

    def __fetch_project_item_event(self):
        # projects_v2_item events carry no repository/issue, so both are looked up to route them like an issue event.
        item = self.payload["projects_v2_item"]
        field_change = self.payload.get("changes", {}).get("field_value")
        if self.payload.get("action") != "edited" or item.get("content_type") != "Issue" or not field_change:
            return None

        try:
            instance = transformer_functions.connect(plugin_info.get_plugin_instance_by_id(self.instance_id, db=self.db))
            org = self.payload["organization"]["login"]
            project_number = field_change["project_number"]

            field_id = next((field["id"] for field in transformer_functions.get_project_fields(instance, org, project_number)
                             if field.get("node_id") == field_change.get("field_node_id")), None)
            if field_id is None:
                as_log.warn("Skipping GitHub Project field change as field [{}] was not found in Project [{}].".format(
                    field_change.get("field_name"), project_number))
                return None

            content = transformer_functions.get_project_item(instance, org, project_number, item["id"])["content"]
            owner, repo = content["repository_url"].split("/repos/", 1)[1].split("/")[:2]
            issue = transformer_functions.get_issue(instance, owner, repo, content["number"])
            repository = transformer_functions.get_repo(instance, owner, repo)
        except Exception as ex:
            as_log.warn("Unable to resolve the issue for GitHub Project item [{}]. The error is [{}].".format(
                item.get("id"), str(ex)))
            return None

        return {
            "action": Event.PROJECT_FIELD_ACTION,
            "issue": issue,
            "repository": repository,
            "sender": self.payload["sender"],
            "projects_v2_item": item,
            "project_field": {
                "name": "projectfield:{}".format(field_id),
                "value": _project_field_value(field_change.get("to")),
            },
        }

    def fetch_project(self, event):
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

    def fetch_query(self, event, project, asset):
        # A No-Project (repository-only) mapping only ever offers the synthetic default asset (see
        # AssetsManage.fetch_assets), so a typed issue must still be able to match it.
        query = super().fetch_query(event, project, asset)
        default_asset = DEFAULT.DEFAULT_ISSUE_TYPE["asset"]
        if asset != default_asset:
            _broaden_asset_match(query, asset, default_asset)
        return query

    def is_cyclic_event(self, event, sync_user):
        return bool(event['sender']['login'] == str(sync_user))


class Event(BaseEvent):

    # 'typed'/'untyped' are deliberately excluded: GitHub fires a separate issues.typed event
    # even when the type is set as part of issue creation, which would otherwise show up as a
    # spurious UPDATE immediately after the CREATE for the same ticket.
    # Synthesized by Payload.fetch_events from a projects_v2_item field edit.
    PROJECT_FIELD_ACTION = 'project_field_changed'

    # Synthesized by Inbound.migrate_update: resend every mapped field from the issue's current state.
    MIGRATE_UPDATE_ACTION = 'migrated'

    UPDATE_ACTIONS = ('edited', 'field_added', 'field_removed', 'assigned',
                      'unassigned', 'labeled', 'unlabeled', 'milestoned', 'demilestoned', PROJECT_FIELD_ACTION,
                      MIGRATE_UPDATE_ACTION)

    # The 'opened' payload can arrive with no type yet, so it can't match a typed mapping; these
    # are sent as CREATE, which the framework skips if the issue is already synced.
    TYPE_ACTIONS = ('typed', 'untyped')

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

        if event_type == 'opened' or event_type in self.TYPE_ACTIONS:
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
        # The issue number (not the global id) is what's usable in GitHub's REST paths, and is
        # what outbound-created issues already store as their display id (see Outbound.create).
        return self.__fetch_issue()['number']

    def fetch_workitem_url(self):
        # Relative to the instance (web) URL, so View Logs opens the issue page on GitHub.
        return urlparse(self.__fetch_issue()['html_url']).path

    def fetch_revision(self):
        return self.__fetch_updated_at()

    # Fired once per value when an issue is created with several labels/assignees, all with the same updated_at.
    BURST_ACTIONS = ('labeled', 'unlabeled', 'assigned', 'unassigned')

    def is_check_duplicate_event(self):
        # Events sharing updated_at carry the same full issue state; only the first one queued is needed.
        return self.event.get("action") in ('opened',) + self.TYPE_ACTIONS + self.BURST_ACTIONS

    def is_sync_this_event(self):
        # Closing an issue deletes its Agility item and sync link, so any later event on the closed issue
        # (e.g. GitHub's "Item closed -> Done" Project automation) would otherwise re-create it there.
        if self.event.get("action") != "closed" and self.__fetch_issue().get("state") == "closed":
            as_log.info("Skipping [{}] event on closed GitHub issue [{}].".format(
                self.event.get("action"), self.__fetch_issue().get("number")))
            return False

        # Project field edits (incl. GitHub's own Project automation) only matter if that field is mapped.
        if self.event.get("action") == self.PROJECT_FIELD_ACTION:
            field_name = self.event["project_field"]["name"]
            if not any((io_field or {}).get("inbound", {}).get("name", "").lower() == field_name
                       for io_field in self.datamap.get("field_mapping", [])):
                return False
        return super().is_sync_this_event()

    def fetch_timestamp(self):
        timestamp = parser.parse(self.__fetch_updated_at())

        return datetime.fromtimestamp(time.mktime(timestamp.utctimetuple())) # type: ignore

    def __fetch_updated_at(self):
        # A Project field edit doesn't touch the issue's updated_at, only the project item's.
        project_item = self.event.get("projects_v2_item") or {}
        return project_item.get("updated_at") or self.__fetch_issue()["updated_at"]


class Inbound(BaseInbound):
    def connect(self):
        try:
            return transformer_functions.connect(
                                                self.instance_details
            )
        except Exception as e:
            error_msg = 'Connection to Demo plugin failed.  Error is [{}].'.format(str(e))
            raise as_exceptions.InboundError(error_msg, stack_trace=True)

    @property
    def absolute_workitem_url(self):
        # Sync reference always uses GitHub's own issue page, even for older instances configured with the API URL.
        issue = self.event.get("sub_issue") or self.event.get("issue") or {}
        return issue.get("html_url") or super().absolute_workitem_url

    def create_remote_link(self, display_id, url, id_field=None, url_field=None):
        repository = self.event["repository"]
        _write_sync_reference(self.instance_object, repository["owner"]["login"], repository["name"],
                              self.workitem_display_id, display_id, url, id_field, url_field,
                              self.assets_info.get("github_project", {}).get("id"))

    def fetch_event_category(self):
        category = []

        event_type = self.event["action"]

        if 'comment' in self.event:
            category.append(EventCategory.COMMENT)
            return category

        if 'sub_issue' in self.event:
            category.append(EventCategory.WORKITEM)
            return category

        if event_type in ('opened', 'closed') + Event.UPDATE_ACTIONS + Event.TYPE_ACTIONS:
            category.append(EventCategory.WORKITEM)

        return category

    def fetch_comment(self):
        if "comment" in self.event:
            return self.event['comment']['body']
        return ""

    # GitHub has no changelog; the action (or "changes" for edited) says which field changed.
    ACTION_CHANGED_FIELDS = {
        "assigned": ("assignee", "assignees"),
        "unassigned": ("assignee", "assignees"),
        "labeled": ("labels",),
        "unlabeled": ("labels",),
        "milestoned": ("milestone",),
        "demilestoned": ("milestone",),
    }

    def normalize_update_fields(self, inbound_field_attr):
        action = self.event.get("action")
        if action == Event.PROJECT_FIELD_ACTION:
            project_field = self.event["project_field"]
            if inbound_field_attr["name"].lower() != project_field["name"]:
                return False, None
            return True, project_field["value"]

        if action == "edited":
            changed_fields = self.event.get("changes", {}).keys()
        elif action == Event.MIGRATE_UPDATE_ACTION:
            return self.__fetch_issue_field_value(inbound_field_attr, allow_empty=True)
        elif action in ("field_added", "field_removed"):
            # The event doesn't say which Issue Field changed; every mapped one is re-read from the issue.
            if not inbound_field_attr["name"].lower().startswith(DEFAULT.ISSUE_FIELD_PREFIX):
                return False, None
            return self.__fetch_issue_field_value(inbound_field_attr, allow_empty=True)
        else:
            changed_fields = self.ACTION_CHANGED_FIELDS.get(action, ())

        if inbound_field_attr["name"].lower() not in changed_fields:
            return False, None

        # The issue in the payload already holds the new value, same as on create.
        return self.__fetch_issue_field_value(inbound_field_attr, allow_empty=True)

    def normalize_create_fields(self, inbound_field_attr):
        return self.__fetch_issue_field_value(inbound_field_attr, allow_empty=False)

    def __fetch_issue_field_value(self, inbound_field_attr, allow_empty):
        # GitHub sends assignees/labels/milestone as objects (or null); Agility needs the plain names.
        issue = self.event.get("issue") or {}
        name = inbound_field_attr["name"].lower()

        if name in ("assignee", "assignees"):
            values = [assignee["login"] for assignee in issue.get("assignees") or []]
            # An empty "set" is skipped by user-field targets as "no user matched"; "" is the platform's reset
            # signal, so the target clears its existing users instead.
            if not values and allow_empty:
                return True, ""
        elif name == "labels":
            values = [label["name"] for label in issue.get("labels") or []]
        elif name == "milestone":
            if issue.get("milestone"):
                return True, issue["milestone"]["title"]
            return (True, "") if allow_empty else (False, None)
        elif name == "body":
            return self.__fetch_body_html(issue.get("body"), allow_empty)
        elif name.startswith(DEFAULT.ISSUE_FIELD_PREFIX):
            return self.__fetch_issue_field(issue, name, inbound_field_attr, allow_empty)
        else:
            return self.get_payload_pattern_value(inbound_field_attr, "create")

        # An empty value on create has nothing to set; on update it clears the field.
        if not values and not allow_empty:
            return False, None
        return True, values

    def __fetch_issue_field(self, issue, name, inbound_field_attr, allow_empty):
        field_id = name[len(DEFAULT.ISSUE_FIELD_PREFIX):]
        field_value = next((value for value in issue.get("issue_field_values") or []
                            if str(value.get("issue_field_id")) == field_id), None)

        value = None
        if field_value:
            if field_value.get("data_type") == "single_select":
                value = (field_value.get("single_select_option") or {}).get("name")
            elif field_value.get("data_type") == "multi_select":
                value = [option["name"] for option in field_value.get("multi_select_options") or []]
            else:
                value = field_value.get("value")

        if value in (None, "", []):
            if not allow_empty:
                return False, None
            return True, [] if inbound_field_attr.get("is_multivalue") else ""
        return True, value

    def __fetch_body_html(self, body, allow_empty):
        if not body:
            return (True, "") if allow_empty else (False, None)

        try:
            return True, transformer_functions.markdown_to_html(
                self.instance_object, body, self.event["repository"]["full_name"])
        except Exception as ex:
            as_log.warn("Unable to render the GitHub description to HTML, syncing it as-is. The error is [{}].".format(
                str(ex)))
            return True, body

    def normalize_listtype_multivalue_field(self, value, field_attr):
        values = list(value or [])
        # "set" replaces the target's current values, which don't exist yet on create (Agility fails reading them).
        if self.event_type == EventTypes.CREATE:
            return [{"act": "add", "field_value": val} for val in values]
        # GitHub always sends the full current set, so on update it replaces whatever Agility has.
        return [{"act": "set", "field_value": values}]

    def normalize_texttype_multivalue_field(self, value, field_attr):
        return self.normalize_listtype_multivalue_field(value, field_attr)

    def normalize_usertype_multivalue_field(self, value, field_attr):
        # GitHub only exposes the login; the target system matches it against its usernames.
        users = [{"username": login} for login in value or []]
        if self.event_type == EventTypes.CREATE:
            return [{"act": "add", "field_value": user} for user in users]
        return [{"act": "set", "field_value": users}]

    def migrate_create(self):
        return [self.__migrate_event("opened")]

    def migrate_update(self):
        return [self.__migrate_event(Event.MIGRATE_UPDATE_ACTION)]

    def __migrate_event(self, action):
        # Rebuilt from the issue's current state when AgilitySync has no record of it in the other system.
        org = self.project_info["project"].split('/')[0]
        repository = self.event.get("repository") or transformer_functions.get_repo(
            self.instance_object, org, self.project_info["display_name"])
        issue = transformer_functions.get_issue(
            self.instance_object, org, repository["name"], self.workitem_display_id)

        return {
            "action": action,
            "issue": issue,
            "repository": repository,
            "sender": self.event.get("sender") or {},
        }

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
        # Project fields live on the project item, not the issue; written after create/update.
        self.__project_field_values = {}
        self.__issue_field_values = {}
        self.__current_issue = None

        for outbound_field in transfome_field_objs:
            if outbound_field.name.lower().startswith(DEFAULT.PROJECT_FIELD_PREFIX):
                self.__project_field_values[outbound_field.name[len(DEFAULT.PROJECT_FIELD_PREFIX):]] = outbound_field.value
                continue
            if outbound_field.name.lower().startswith(DEFAULT.ISSUE_FIELD_PREFIX):
                # Issue Fields have their own API; written after the issue is created/updated.
                self.__issue_field_values[outbound_field.name[len(DEFAULT.ISSUE_FIELD_PREFIX):]] = \
                    self.__issue_field_api_value(outbound_field)
                continue

            field_name = outbound_field.name.lower()
            if outbound_field.is_multivalue:
                values = self.__multivalue_values(
                    outbound_field.value, self.__fetch_current_multivalues(field_name, outbound_field.value))
                if field_name == "assignee":
                    # GitHub's "assignee" only takes a single login; "assignees" takes the list.
                    create_fields["assignees"] = values
                else:
                    create_fields[field_name] = values
            elif field_name == "milestone":
                create_fields["milestone"] = self.__fetch_milestone_number(outbound_field.value)
            else:
                create_fields[field_name] = outbound_field.value

        if create_fields.get("body"):
            try:
                create_fields["body"] = transformer_functions.html_to_markdown(create_fields["body"])
            except Exception as ex:
                as_log.warn("Unable to convert the description to Markdown, syncing it as HTML. The error is [{}].".format(
                    str(ex)))

        # The synthetic default asset has no corresponding organization issue type to set.
        if self.asset_info.get("id") != DEFAULT.DEFAULT_ISSUE_TYPE["id"]:
            create_fields["type"] = self.asset_info["asset"]
        return create_fields

    def __issue_field_api_value(self, outbound_field):
        if outbound_field.is_multivalue:
            return self.__multivalue_values(
                outbound_field.value, self.__fetch_current_multivalues(outbound_field.name.lower(), outbound_field.value))

        value = outbound_field.value
        if value in (None, ""):
            return None
        if outbound_field.datatype == FieldTypes.NUMERIC:
            return float(value)
        if outbound_field.datatype in (FieldTypes.DATE, FieldTypes.DATETIME):
            return str(value)[:10]
        return str(value)

    def __sync_issue_fields(self, org, repo, issue_number):
        if not self.__issue_field_values:
            return

        values = [{"field_id": int(field_id), "value": value}
                  for field_id, value in self.__issue_field_values.items() if value not in (None, [])]
        if values:
            transformer_functions.add_issue_field_values(self.instance_object, org, repo, issue_number, values)

        for field_id, value in self.__issue_field_values.items():
            if value in (None, []) and self.inbound.event_type == EventTypes.UPDATE:
                try:
                    transformer_functions.delete_issue_field_value(self.instance_object, org, repo, issue_number, field_id)
                except Exception as ex:
                    # GitHub returns 404 when the field had no value to clear.
                    as_log.debug("Issue field [{}] not cleared: [{}].".format(field_id, str(ex)))

    def transform_usertype_multivalue(self, value, field_obj):
        # Incoming users are {"username"/"email"} docs; GitHub assignees are plain logins.
        def login(user):
            return (user.get("username") or user.get("email")) if isinstance(user, dict) else user

        docs = []
        for value_doc in value or []:
            field_value = value_doc.get("field_value")
            if isinstance(field_value, list):
                field_value = [login(user) for user in field_value]
            else:
                field_value = login(field_value)
            docs.append(dict(value_doc, field_value=field_value))
        return docs

    def __fetch_milestone_number(self, title):
        # GitHub's issue API takes the milestone number; the mapping works with titles.
        if not title:
            return None

        org = self.project_info["project"].split('/')[0]
        milestones = transformer_functions.get_field_value(
            self.instance_object, details=self.instance_details, repo=self.project_info["display_name"], org=org)
        for milestone in milestones:
            if milestone["title"] == title:
                return milestone["number"]
        raise as_exceptions.OutboundError(
            "Milestone [{}] does not exist in repository [{}].".format(title, self.project_info["display_name"]))

    def __fetch_current_multivalues(self, field_name, value_docs):
        # GitHub replaces labels/assignees with the list sent, so add/remove changes must start from what's there.
        if (self.inbound.event_type != EventTypes.UPDATE or not value_docs
                or value_docs[0].get("act") == "set"):
            return []

        if self.__current_issue is None:
            org = self.project_info["project"].split('/')[0]
            self.__current_issue = transformer_functions.get_issue(
                self.instance_object, org, self.project_info["display_name"], self.__fetch_issue_number())

        if field_name == "assignee":
            return [assignee["login"] for assignee in self.__current_issue.get("assignees") or []]
        if field_name == "labels":
            return [label["name"] for label in self.__current_issue.get("labels") or []]
        if field_name.startswith(DEFAULT.ISSUE_FIELD_PREFIX):
            field_id = field_name[len(DEFAULT.ISSUE_FIELD_PREFIX):]
            for field_value in self.__current_issue.get("issue_field_values") or []:
                if str(field_value.get("issue_field_id")) == field_id:
                    return [option["name"] for option in field_value.get("multi_select_options") or []]
        return []

    @staticmethod
    def __multivalue_values(value_docs, current_values):
        # Framework format: [{"act": "set", "field_value": [...]}] or [{"act": "add"/"remove", "field_value": v}, ...]
        values = list(current_values)
        for value_doc in value_docs or []:
            field_value = value_doc.get("field_value")
            if value_doc.get("act") == "set":
                values = [val for val in (field_value or []) if val not in (None, "")]
            elif value_doc.get("act") == "add" and field_value not in (None, "") and field_value not in values:
                values.append(field_value)
            elif value_doc.get("act") == "remove" and field_value in values:
                values.remove(field_value)
        return values

    def create(self, sync_fields):

        try:
            ticket = transformer_functions.tickets(self.instance_object
                                         ,payload =sync_fields, details=self.instance_details,repo =self.project_info["display_name"],id =self.project_info["project"])
            orgsplit = self.project_info["project"].split('/')
            org = orgsplit[0]

            project_item = self.__add_to_github_project(org, {"type": "Issue", "id": ticket["id"]})
            if project_item:
                try:
                    self.__sync_project_fields(org, project_item["id"])
                except Exception as ex:
                    # The issue already exists; failing here would create a duplicate on resync.
                    as_log.warn("Unable to set GitHub Project field values on issue [{}]. The error is [{}].".format(
                        ticket["number"], str(ex)))
            self.__sync_parent_relationship(org, ticket["id"])

            try:
                self.__sync_issue_fields(org, self.project_info["display_name"], ticket["number"])
            except Exception as ex:
                # The issue already exists; failing here would create a duplicate on resync.
                as_log.warn("Unable to set GitHub Issue field values on issue [{}]. The error is [{}].".format(
                    ticket["number"], str(ex)))

            sync_info = {
                "project":  self.project_info["project"],
                "issuetype": "issues",
                "synced_fields": sync_fields
            }
            xref_object = {
                "relative_url": urlparse(ticket["html_url"]).path,
                # Kept as the int from GitHub's JSON: inbound webhooks look the link up by this exact value.
                'id': ticket["id"],
                # the issue number (not the global id) is what's directly usable in GitHub's REST
                # paths, and is what the relationship lookup resolves to for a parent issue.
                'display_id': str(ticket["number"]),
                'sync_info': sync_info,
            }
            xref_object["absolute_url"] = ticket["html_url"]
            return xref_object

        except Exception as e:
            error_msg = ("Unable to create [{}] in Github. Error is [{}].\n Trying to sync fields \n"
                         "[{}]\n.".format(self.asset_info["display_name"], e, sync_fields))
            raise as_exceptions.OutboundError(error_msg, stack_trace=True)

    def __add_to_github_project(self, org, item):
        # Returns the new project item, or None (e.g. 422 if the issue is already in the Project).
        github_project = self.assets_info.get("github_project", {})
        if github_project.get("id") in (None, DEFAULT.NO_PROJECT_ID):
            return None

        try:
            return transformer_functions.add_project_item(self.instance_object, org, github_project["id"], item)
        except Exception as ex:
            as_log.warn("Unable to add the issue to GitHub Project [{}]. The error is [{}].".format(
                github_project.get("display_name"), str(ex)))
            return None

    def __sync_project_fields(self, org, item_id):
        if not self.__project_field_values:
            return

        project_number = self.assets_info["github_project"]["id"]
        project_fields = {str(field["id"]): field for field in
                          transformer_functions.get_project_fields(self.instance_object, org, project_number)}

        updates = []
        for field_id, value in self.__project_field_values.items():
            field = project_fields.get(field_id)
            if field is None:
                as_log.warn("Skipping GitHub Project field [{}] as it no longer exists in the Project.".format(field_id))
                continue
            updates.append({"id": field["id"], "value": _project_field_api_value(field, value)})

        if updates:
            transformer_functions.update_project_item(
                self.instance_object, org, project_number, item_id, {"fields": updates})

    def __fetch_issue_number(self):
        # The stored xref id is GitHub's global issue id, which is not usable in the per-repo REST
        # paths below - the issue number is recovered from the end of the stored relative_url
        # ("/{org}/{repo}/issues/{number}", or "repos/{org}/{repo}/issues/{number}" for older links) instead.
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
            as_log.warn("Unable to sync parent/sub-issue relationship for issue [{}]. The error is [{}].".format(
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

        if self.__project_field_values:
            try:
                item_id = transformer_functions.find_issue_project_item_id(
                    self.instance_object, org, self.project_info["display_name"], issue_number,
                    self.assets_info.get("github_project", {}).get("id"))
                if item_id is None:
                    project_item = self.__add_to_github_project(org, {"type": "Issue", "id": int(self.workitem_id)})
                    item_id = project_item["id"] if project_item else None
                if item_id is None:
                    raise Exception("the issue is not in the mapping's GitHub Project")
                self.__sync_project_fields(org, item_id)
            except Exception as e:
                raise as_exceptions.OutboundError(
                    "Unable to sync GitHub Project fields on issue [{}]. Error is [{}].".format(issue_number, e),
                    stack_trace=True)

        try:
            self.__sync_issue_fields(org, self.project_info["display_name"], issue_number)
        except Exception as e:
            raise as_exceptions.OutboundError(
                "Unable to sync GitHub Issue fields on issue [{}]. Error is [{}].".format(issue_number, e),
                stack_trace=True)

        self.__sync_parent_relationship(org, self.workitem_id)

    def delete(self):
        # GitHub's REST API can't delete issues, so a delete from the other system closes the issue instead.
        issue_number = self.__fetch_issue_number()
        org = self.project_info["project"].split('/')[0]

        try:
            transformer_functions.update_ticket(
                self.instance_object, org, self.project_info["display_name"], issue_number,
                {"state": "closed", "state_reason": "not_planned"})
        except Exception as e:
            status = getattr(getattr(self.instance_object, '_response_obj', None), 'status_code', None)
            # 404/410: the issue was already deleted or transferred, so there is nothing left to close.
            if status in (404, 410):
                as_log.warn("GitHub issue [{}] no longer exists; skipping close. Error is [{}].".format(
                    issue_number, e))
                return
            raise as_exceptions.OutboundError(
                "Unable to close GitHub issue [{}]. Error is [{}].".format(issue_number, e), stack_trace=True)

    def create_remote_link(self, workitem_id, url, id_field=None, url_field=None):
        _write_sync_reference(self.instance_object, self.project_info["project"].split('/')[0],
                              self.project_info["display_name"], self.workitem_display_id,
                              workitem_id, url, id_field, url_field,
                              self.assets_info.get("github_project", {}).get("id"))

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
        # search_query rules: bare "field='value'" conditions are AND'd (and_operator is a plain
        # space), while a "(cond OR cond ...)" group is an OR alternative (or_operator is " OR ").
        # GitHub's search API has no OR support across qualifiers, so each OR alternative is run as
        # its own AND-only search and the results are merged, preserving the configured semantics.
        or_groups = [group for group in (
            self.__parse_conditions(raw_group) for raw_group in re.findall(r"\(([^)]*)\)", search_query)) if group]
        and_conditions = self.__parse_conditions(re.sub(r"\([^)]*\)", "", search_query))

        if not and_conditions and not or_groups:
            return None

        org = self.project_info["project"].split('/')[0]
        repo = self.project_info["display_name"]

        matches = {}
        for or_combination in itertools.product(*or_groups):
            qualifiers = self.__build_qualifiers(and_conditions + list(or_combination))

            try:
                results = transformer_functions.search_issues(self.instance_object, org, repo, qualifiers)
            except Exception as e:
                raise as_exceptions.OutboundError(
                    "Unable to search for an existing issue in Github. Error is [{}].".format(e), stack_trace=True)

            for issue in results.get("items", []):
                matches[issue["id"]] = issue

        if not matches:
            return None
        if len(matches) > 1:
            raise as_exceptions.OutboundError(
                "Multiple matching Github issues found while searching before create. Query was [{}].".format(
                    search_query))

        issue = next(iter(matches.values()))
        return {
            "relative_url": urlparse(issue["html_url"]).path,
            "id": issue["id"],
            "display_id": str(issue["number"]),
            "sync_info": {},
            "absolute_url": issue["html_url"],
        }

    @staticmethod
    def __parse_conditions(segment):
        return [(name, value) for name, value in re.findall(r"(\w+)\s*[=~]\s*'([^']*)'", segment) if value]

    @staticmethod
    def __build_qualifiers(conditions):
        return ' '.join(
            'in:title "{}"'.format(value) if name == "title" else '{}:"{}"'.format(name, value)
            for name, value in conditions)
