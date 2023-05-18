import base64

from external_plugins.github_integrate import default as DEFAULT 
from agilitysync.external_lib.restapi import ASyncRestApi


def connect(instance_details):
   return ASyncRestApi(instance_details['url'],headers={
                            "authorization": "Bearer {}".format(instance_details["token"]),
                            "Accept": "application/json",
                            "Content-Type": "application/json"
                            })


#def encode_to_base64_string(email, password):
    #data = email + ":" + password
    #data_bytes = data.encode('ascii')
    #base64_bytes = base64.b64encode(data_bytes)
    #return base64_bytes.decode("utf-8")


def check_connection(instance,instance_details):
    instance_path = "repos"

    path = "{}".format(
            DEFAULT.INITIAL_PATH, 
            
            )

    response = instance.get(path)

    if instance_details["Username"] == response["login"]:
        return "Connection to Github server is successfull."
    else:
        return response

def get_repos(instance,details):
    instance_path = "repos"
    path = "{}/{}/{}".format(
        "orgs", 
        details["Organization"], 
        instance_path)
    response = instance.get(path)
    return response

def tickets(instance):
    instance_path = "orgs"
    path = "{}/{}".format(
        DEFAULT.INITIAL_PATH, 
        ##DEFAULT.REST_ENDPOINT_VERSION, 
        instance_path)
    response = instance.get(path)
    return response[0]["url"]


def ticket_fields(instance, id=None, payload=None):
    tickets = [
        {
        'asset':"issues",
        'display_name': "issues",
        'id': "Assettype-001"
        }
    ]
    return tickets


def get_user_by_email(instance, email):
    instance_path = "search?query=type:user \"{}\"".format(email)
    path = "{}/{}/{}".format(
        DEFAULT.INITIAL_PATH, 
        DEFAULT.REST_ENDPOINT_VERSION,
        instance_path)

    response = instance.get(path)
    return response


def webhooks(instance, id=None, payload=None):
    instance_path = "webhooks/{}".format(id) if id else "webhooks"
    path = "{}/{}/{}".format(
        DEFAULT.INITIAL_PATH, 
        DEFAULT.REST_ENDPOINT_VERSION, 
        instance_path)

    if payload:
        if id:
            response = instance.put(path, payload)
        else:
            response = instance.post(path, payload)
        return response["webhook"]
    else:
        response = instance.get(path)
        return response["webhooks"]


def trigger_categories(instance, id=None, payload=None):
    instance_path = ("trigger_categories/{}".format(id)
                     if id else "trigger_categories")

    path = "{}/{}/{}".format(
        DEFAULT.INITIAL_PATH, 
        DEFAULT.REST_ENDPOINT_VERSION, 
        instance_path)

    if payload:
        response = instance.post(path, payload)
        return response["trigger_category"]
    else:
        response = instance.get(path)
        return response["trigger_categories"]


def triggers(instance, id=None, payload=None):
    instance_path = ("triggers/{}".format(id)
                     if id else "triggers")

    path = "{}/{}/{}".format(
        DEFAULT.INITIAL_PATH, 
        DEFAULT.REST_ENDPOINT_VERSION, 
        instance_path)

    if payload:
        response = (instance.put(path, payload) if
                    id else instance.post(path, payload))
        return response["trigger"]
    else:
        response = instance.get(path)
        return response["triggers"]
