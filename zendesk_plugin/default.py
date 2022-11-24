REST_ENDPOINT_VERSION = "v2"

INITIAL_PATH = "api"

TRIGGER_CATEGORY_NAME = "All AS Triggers"

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
