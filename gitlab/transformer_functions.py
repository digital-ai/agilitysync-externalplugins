import base64

from external_plugins.gitlab import default as DEFAULT 
from agilitysync.external_lib.restapi import ASyncRestApi

fields = [
    {
    "required": True,
    "disabled field": False,
    "customfield" : False,
    "raw_title": "title",
    "title": "title",
    "type": "title",
    "IsMultivalue" : False
},
{
    "required": False,
    "disabled field": False,
    "customfield": False,
    "raw_title": "description",
    "title": "description",
    "type": "description",
    "IsMultivalue" : False
},

{
    "required": False,
    "disabled field": False,
    "customfield": False,
    "raw_title": "labels",
    "title": "labels",
    "type": "labels",
    "IsMultivalue" : False
},
{
    "required": False,
    "disabled field": False,
    "customfield":False,
    "raw_title": "weight",
    "title": "weight",
    "type": "weight",
    "IsMultivalue" : False
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

def check_connection(instance,instance_details):
    path = "{}".format(
            DEFAULT.INITIAL_PATH,
            instance_details["Username"] 
            
            )

    response = instance.get(path)

    if instance_details["Username"] == response["username"]:
        return "Connection to Gitlab server is successfull."
    else:
        return response["error"]

def get_org(instance):
    instance_path = "groups"
    path = "{}".format(
        
         instance_path)
    response = instance.get(path)
    return response

def get_repos(instance,details):
    instance_path = "projects"
    path = "{}/{}/{}".format(
        "groups", 
        details, 
        instance_path)
    response = instance.get(path)
    return response

def tickets(instance,payload,id):
    
     
    orgsplit = id.split('/')
    org = orgsplit[1]
    path = "{}/{}/{}".format(
        "projects", 
        org, 
        "issues"
        )
    if payload:
        response = (instance.post(path, payload))
                
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


def webhooks(instance, id, payload=None):
    instance_path = "hooks"
    orgsplit = id.split('/')
    org = orgsplit[1]
    path = "{}/{}/{}".format(
        "projects", 
        org, 
        instance_path)

    if payload:
        
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
