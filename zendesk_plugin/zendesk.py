import requests
import base64

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
        full_url = "{}/api/{}/organizations".format(self.url, self.rest_endpoint)
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
        assets = []
        for id in ids:
            tickets = self.fetch_tickets().get("tickets")
            for ticket in tickets:
                project_tag = "project_" + str(id)
                if (project_tag in ticket["tags"] and "project_child" in ticket["tags"]):
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






# url = "https://ukagent.zendesk.com"
# api_token = "Zml4aWs0MTc0N0B1a2dlbnQuY29tOmFkbWluQDEyMzQ="

# print(check_connection(url, api_token))
