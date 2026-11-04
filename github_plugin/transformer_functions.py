import base64
from urllib.parse import urlencode


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
    "IsMultivalue" : True
},
{
    "required": False,
    "disabled field": False,
    "customfield":False,
    "raw_title": "Labels",
    "title":"labels",
    "type":"labels",
    "IsMultivalue" : True
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
def connect(instance_details):
   return ASyncRestApi(instance_details['url'],headers={
                            "authorization": "Bearer {}".format(instance_details["token"]),
                            "Accept": "application/json",
                            "Content-Type": "application/json"
                            })


def check_connection(instance, instance_details):
    path = "{}".format(DEFAULT.INITIAL_PATH)

    response = instance.get(path)

    if instance_details["Username"] != response["login"]:
        return response.get("message", "Unable to verify the Github user.")

    org = instance_details.get("organization")
    if org:
        try:
            get_org_info(instance, org)
        except Exception:
            return "Unable to access the GitHub organization [{}] with the provided token.".format(org)

    return "Connection to Github server is successfull."


def get_org_info(instance, org):
    path = "{}/{}".format("orgs", org)
    response = instance.get(path)
    return response


def get_field_value(instance, details, repo, org):
    instance_path = "milestones"
    path = "{}/{}/{}/{}".format(
        "repos",
        org, repo,
        instance_path)
    response = instance.get(path)
    return response


def get_repos(instance, org):
    instance_path = "repos"
    path = "{}/{}/{}".format(
        "orgs",
        org,
        instance_path)
    response = instance.get(path)
    return response


def get_projects_v2(instance, org):
    path = "orgs/{}/projectsV2".format(org)
    response = instance.get(path)
    return response


def get_project_fields(instance, org, project_number):
    path = "orgs/{}/projectsV2/{}/fields".format(org, project_number)
    response = instance.get(path)
    return response


def add_project_item(instance, org, project_number, payload):
    path = "orgs/{}/projectsV2/{}/items".format(org, project_number)
    response = instance.post(path, payload)
    return response


def update_project_item(instance, org, project_number, item_id, payload):
    path = "orgs/{}/projectsV2/{}/items/{}".format(org, project_number, item_id)
    response = instance.patch(path, payload)
    return response


def get_issue_types(instance, org):
    path = "orgs/{}/issue-types".format(org)
    response = instance.get(path)
    return response.get("issue_types", response) if isinstance(response, dict) else response

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


def update_ticket(instance, org, repo, issue_number, payload):
    path = "repos/{}/{}/issues/{}".format(org, repo, issue_number)
    response = instance.patch(path, payload)
    return response


def add_issue_comment(instance, org, repo, issue_number, comment):
    path = "repos/{}/{}/issues/{}/comments".format(org, repo, issue_number)
    response = instance.post(path, {"body": comment})
    return response


def add_sub_issue(instance, org, repo, parent_issue_number, sub_issue_id):
    path = "repos/{}/{}/issues/{}/sub_issues".format(org, repo, parent_issue_number)
    response = instance.post(path, {"sub_issue_id": int(sub_issue_id)})
    return response


def remove_sub_issue(instance, org, repo, parent_issue_number, sub_issue_id):
    path = "repos/{}/{}/issues/{}/sub_issue".format(org, repo, parent_issue_number)
    response = instance.delete(path, {"sub_issue_id": int(sub_issue_id)})
    return response


def search_issues(instance, org, repo, qualifiers):
    query = "repo:{}/{} is:issue {}".format(org, repo, qualifiers)
    query_str = urlencode({"q": query, "per_page": 2})
    response = instance.get("search/issues", query_str=query_str)
    return response


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


def org_webhooks(instance, org, payload=None):
    path = "orgs/{}/hooks".format(org)

    if payload:
        response = instance.post(path, payload)
        return response
    else:
        response = instance.get(path)
        return response


def update_repo_webhook_events(instance, org, repo, hook_id, events):
    path = "repos/{}/{}/hooks/{}".format(org, repo, hook_id)
    response = instance.patch(path, {"events": events})
    return response


def update_org_webhook_events(instance, org, hook_id, events):
    path = "orgs/{}/hooks/{}".format(org, hook_id)
    response = instance.patch(path, {"events": events})
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
