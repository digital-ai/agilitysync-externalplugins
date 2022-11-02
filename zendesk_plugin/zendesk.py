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

    def request(self, method, path, payload=None):
        url = "{}/api/{}/{}".format(self.url, self.rest_endpoint_version, path)

        headers = {
            'Authorization': self.token,
            'Content-Type': 'application/json'
        }

        if method in ["POST", "PUT"]:
            response = requests.request(method, url, headers=headers, data=json.dumps(payload))
        elif method in ["GET"]:
            response = requests.request(method, url, headers=headers)

        if (response.status_code not in [200, 201]):
            raise Exception(response.json())
        return response.status_code, response.json()

    def check_connection(self):
        status_code, response = self.request("GET", "organizations")

        if (status_code in [200]):
            return "Connection to Zendesk server is successfull."
        else:
            return "Can not establish connection to Zendesk server."

    def tickets(self, id=None):
        # fetch_tickets, fetch_tickets_on_id
        path = "tickets/{}".format(id) if id else "tickets"

        status_code, response = self.request("GET", path)
        return response

    def _meta_request(self, path):
        status_code, response = self.request("GET", path)
        return response

    def ticket_fields(self, id=None):
        path = "ticket_fields/{}".format(id) if id else "ticket_fields"
        status_code, response = self.request("GET", path)
        return response["ticket_fields"]

    def get_user_by_email(self, email):
        path = "search?query=type:user \"{}\"".format(email)

        status_code, response = self.request("GET", path)
        return response

    def webhook(self, destination_endpoint_url, webhook_name, webhook_description, id=None):
        path = "webhooks/{}".format(id) if id else "webhooks"

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

        status_code, response = self.request("POST", path, payload)
        return response["webhook"]

    def trigger_categories(self, id=None, payload=None):
        path = "trigger_categories/{}".format(id) if id else "trigger_categories"

        if payload:
            status_code, response = self.request("POST", path, payload)
            return response["trigger_category"]
        else:
            status_code, response = self.request("GET", path)
            return response["trigger_categories"]

    def triggers(self, id=None, payload=None):
        path = "triggers/{}".format(id) if id else "triggers"

        if payload:
            if id:
                status_code, response = self.request("PUT", path, payload)
            else:
                status_code, response = self.request("POST", path, payload)

            return response["trigger"]
        else:
            status_code, response = self.request("GET", path)
            return response["triggers"]
