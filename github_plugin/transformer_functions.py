import base64

from external_plugins.github_integrate import default as DEFAULT 
from agilitysync.external_lib.restapi import ASyncRestApi

fields = [
    {
    "required": True,
    "disabled field": False,
    "customfield":False,
    "raw_title": "title",
    "title":"title",
    "type":"title",
    "IsMultivalue" : False
},
{
    "required": False,
    "disabled field": False,
    "customfield":False,
    "raw_title": "assignee",
    "title":"assignee",
    "type":"assignee",
    "IsMultivalue" : False
},
{
    "required": False,
    "disabled field": False,
    "customfield":False,
    "raw_title": "Labels",
    "title":"labels",
    "type":"labels",
    "IsMultivalue" : False
},
{
    "required": False,
    "disabled field": False,
    "customfield":False,
    "raw_title": "Milestone",
    "title":"milestone",
    "type":"milestone",
    "IsMultivalue" : True
},

]
def ticfields(self):
    return fields
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
def get_field_value(instance,details,repo):
    instance_path = "milestones"
    path = "{}/{}/{}/{}".format(
        "repos",
        details["Organization"],repo,
         instance_path)
    response = instance.get(path)
    return response

def get_org(instance):
    instance_path = "orgs"
    path = "{}/{}".format(
        "user", 
         instance_path)
    response = instance.get(path)
    return response

def get_repos(instance,details):
    instance_path = "repos"
    path = "{}/{}/{}".format(
        "orgs", 
        details["Organization"], 
        instance_path)
    response = instance.get(path)
    return response

def tickets(instance,payload,repo,details,id=None):
    instance_path = "issues/{}".format(id) if id else ""
    path = "{}/{}/{}/{}".format(
        "repos", 
         details["Organization"], 
        repo,"issues"
        )
    if payload:
        response = (instance.patch(path, payload)
                    if id else instance.post(path, payload))
        return response
    else:
        response = instance.get(path)
        return response


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


def webhooks(instance,instance_details,repo, id=None, payload=None):
    instance_path = "hooks"
    path = "{}/{}/{}/{}".format(
        "repos", 
        instance_details["Organization"],
        repo, 
        instance_path)

    if payload:
        if id:
            response = instance.put(path, payload)
        else:
            response = instance.post(path, payload)
        return response
    else:
        response = instance.get(path)
        return response


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
