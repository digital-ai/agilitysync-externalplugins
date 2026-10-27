REST_ENDPOINT_VERSION = "orgs"

INITIAL_PATH = "user"

TRIGGER_CATEGORY_NAME = "All AS Triggers"

# Sentinel used when a mapping is configured without a GitHub Project (v2), i.e. repository only.
NO_PROJECT_ID = "no_project"
NO_PROJECT_DISPLAY_NAME = "No Project"

# Synthetic issue type that is always available, used both when no real Project is selected and
# prepended to the real issue-type list fetched from GitHub when a Project is selected.
DEFAULT_ISSUE_TYPE = {
    "id": "issue",
    "asset": "Issue",
    "display_name": "Issue"
}

# Predefined fields available for every mapping (title/assignee/labels/milestone) are defined
# directly in transformer_functions.fields.

ISSUES_WEBHOOK_EVENTS = ["issues", "sub_issues"]
PROJECT_WEBHOOK_EVENTS = ["issues", "projects_v2_item", "sub_issues"]
COMMENT_WEBHOOK_EVENT = "issue_comment"

AS_TRIGGERS = [
    {
        "title": "AS-Ticket-Create-Trigger",
        "webhook_type": "ticket_created",
        "conditions_value": "Create"
    },
    {
        "title": "AS-Ticket-Update-Trigger",
        "webhook_type": "ticket_updated",
        "conditions_value": "Change"
    }
]
