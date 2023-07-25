import base64


from external_plugins.github_plugin import default as DEFAULT 
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





def check_connection(instance,instance_details):
    instance_path = "repos"

    path = "{}".format(
            DEFAULT.INITIAL_PATH, 
            
            )

    response = instance.get(path)

    if instance_details["Username"] == response["login"]:
        return "Connection to Github server is successfull."
    else:
        return response["message"]
def get_field_value(instance,details,repo,org):
    instance_path = "milestones"
    orgsplit = org.split('/')
    org = orgsplit[0]
    path = "{}/{}/{}/{}".format(
        "repos",
        org,repo,
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
        details, 
        instance_path)
    response = instance.get(path)
    return response

def tickets(instance,payload,repo,details,id=None):
    instance_path = "issues"
     
    orgsplit = id.split('/')
    org = orgsplit[0]
    path = "{}/{}/{}/{}".format(
        "repos", 
        org, 
        repo,"issues"
        )
    if payload:
        response = instance.post(path, payload)
                   
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


def webhooks(instance,repo, id, payload=None):
    instance_path = "hooks"
    orgsplit = id.split('/')
    org = orgsplit[0]
    path = "{}/{}/{}/{}".format(
        "repos", 
        org,
        repo, 
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
