import requests
import base64
import json

class Zendesk:
    def __init__(self, url, email, password):
        self.url = url
        self.email = email
        self.password = password
        self.token = "Basic " + self.encode_to_base64_string()
        self.rest_endpoint_version = "v2"

    def encode_to_base64_string(self):
        data = self.email + ":" + self.password
        data_bytes = data.encode('ascii')
        base64_bytes = base64.b64encode(data_bytes)
        return base64_bytes.decode("utf-8")

    def check_connection(self):
        full_url = "{}/api/{}/organizations".format(self.url, self.rest_endpoint_version)
        headers = {
            'Authorization': self.token
        }
        response = requests.request("GET", full_url, headers=headers)
        if (response.status_code in [200]):
            return "Connection to Zendesk server is successfull."
        else:
            return "Can not establish connection to Zendesk server."

    def fetch_tickets(self):
        full_url = "{}/api/{}/tickets.json".format(self.url, self.rest_endpoint_version)
        headers = {
            'Authorization': self.token
        }
        response = requests.request("GET", full_url, headers=headers)
        if (response.status_code in [200]):
            return response.json()

    def _meta_request(self, path):
        full_url = "{}/api/{}/{}".format(self.url, self.rest_endpoint_version, path)
        headers = {
            'Authorization': self.token
        }
        response = requests.request("GET", full_url, headers=headers)
        if (response.status_code in [200]):
            return response.json()
    
    def fetch_tickets_on_id(self, id):
        full_url = "{}/api/{}/tickets/{}".format(self.url, self.rest_endpoint_version, id)
        headers = {
            'Authorization': self.token
        }
        response = requests.request("GET", full_url, headers=headers)
        if (response.status_code in [200]):
            return response.json()
    
    def get_assets(self, ids):
        # Zendesk has only default ticket type. If we need to add more ticket types
        # we have to go for custom field option.
        # So written code with custom asset type.
        CUSTOM_ASSET_FIELD_ID = "10007972126609"
        # CUSTOM_ASSET_FIELD_ID = "" # Need to uncomment
        assets = []
        for id in ids:
            tickets = self.fetch_tickets().get("tickets")
            for ticket in tickets:
                project_tag = "project_" + str(id)
                if CUSTOM_ASSET_FIELD_ID:
                    for custom_asset in ticket["custom_fields"]:
                        if str(custom_asset["id"]) == CUSTOM_ASSET_FIELD_ID:
                            if custom_asset["value"] not in assets:
                                assets.append(custom_asset["value"])
                else:
                    if ticket["type"] not in assets:
                        assets.append(ticket["type"])

        return assets

    def fetch_fields(self):
        full_url = "{}/api/{}/ticket_fields".format(self.url, self.rest_endpoint_version)
        headers = {
            'Authorization': self.token
        }
        response = requests.request("GET", full_url, headers=headers)
        if (response.status_code in [200]):
            return response.json()

    def get_user_by_email(self, email):
        full_url = "{}/api/{}/users/search?query={}".format(self.url, self.rest_endpoint_version, self.email)
        headers = {
            'Authorization': self.token
        }
        response = requests.request("GET", full_url, headers=headers)
        if (response.status_code in [200]):
            return response.json()
    
    def webhook_post(self, destination_endpoint_url, webhook_name, webhook_description):
        # https://{subdomain}.zendesk.com/api/v2/webhooks
        full_url = "{}/api/{}/webhooks".format(self.url, self.rest_endpoint_version)
        headers = {
            'Authorization': self.token
        }
        payload = {
            "webhook": {
                "endpoint": "{}".format(destination_endpoint_url),
                "http_method": "POST",
                "name": "{}".format(webhook_name),
                "status": "active",
                "request_format": "json",
                "subscriptions": ["conditional_ticket_events"]
            }
        }
        response = requests.request("POST", full_url, headers=headers, data=json.dumps(payload))
        if (response.status_code in [201]):
            return response.json()
        else:
            response = response.json()
            raise Exception(response)
