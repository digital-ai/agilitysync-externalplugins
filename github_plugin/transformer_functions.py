import base64
from urllib.parse import urlencode, urlparse


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
    "raw_title": "body",
    "title":"description",
    "type":"body",
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
    "raw_title": "labels",
    "title":"labels",
    "type":"labels",
    "IsMultivalue" : True
},
{
    "required": False,
    "disabled field": False,
    "customfield":False,
    "raw_title": "milestone",
    "title":"milestone",
    "type":"milestone",
    "IsMultivalue" : False
},

]
def api_base_url(url):
    # The instance URL is the GitHub web address (so work item links open the issue page); the REST API
    # lives at api.github.com for GitHub.com and at <host>/api/v3 for GitHub Enterprise Server.
    # API URLs from older instances are used as-is.
    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    host = parsed.netloc or parsed.path.split("/")[0]
    path = parsed.path.rstrip("/") if parsed.netloc else ""

    if host.startswith("api.") or path.endswith("/api/v3"):
        return "{}://{}{}".format(scheme, host, path)
    if host in ("github.com", "www.github.com"):
        return "https://api.github.com"
    return "{}://{}/api/v3".format(scheme, host)


def connect(instance_details):
   return ASyncRestApi(api_base_url(instance_details['url']),headers={
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


def get_labels(instance, org, repo):
    path = "repos/{}/{}/labels".format(org, repo)
    return instance.get(path, query_str="per_page=100")


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


def get_project_item(instance, org, project_number, item_id):
    path = "orgs/{}/projectsV2/{}/items/{}".format(org, project_number, item_id)
    return instance.get(path)


def find_issue_project_item_id(instance, org, repo, issue_number, project_number):
    # REST has no issue -> project item lookup; GraphQL's databaseId is the REST item id.
    query = ("query($owner: String!, $repo: String!, $number: Int!) { repository(owner: $owner, name: $repo) {"
             " issue(number: $number) { projectItems(first: 50, includeArchived: true) {"
             " nodes { databaseId project { number } } } } } }")
    # GraphQL lives at /graphql on github.com and /api/graphql on Enterprise (REST base /api/v3).
    base_url = instance.base_url[:-len("/v3")] if instance.base_url.endswith("/v3") else instance.base_url
    response = instance.post("graphql", {"query": query, "variables": {
        "owner": org, "repo": repo, "number": int(issue_number)}}, base_url=base_url)

    if response.get("errors"):
        raise Exception(response["errors"])

    issue = ((response.get("data") or {}).get("repository") or {}).get("issue") or {}
    for node in (issue.get("projectItems") or {}).get("nodes") or []:
        if str((node.get("project") or {}).get("number")) == str(project_number):
            return node["databaseId"]
    return None


def get_issue(instance, org, repo, issue_number):
    path = "repos/{}/{}/issues/{}".format(org, repo, issue_number)
    return instance.get(path)


def get_repo(instance, org, repo):
    path = "repos/{}/{}".format(org, repo)
    return instance.get(path)


def get_issue_types(instance, org):
    path = "orgs/{}/issue-types".format(org)
    response = instance.get(path)
    return response.get("issue_types", response) if isinstance(response, dict) else response


def get_issue_fields(instance, org):
    path = "orgs/{}/issue-fields".format(org)
    response = instance.get(path)
    return response


def add_issue_field_values(instance, org, repo, issue_number, values):
    # POST adds/overwrites only the given fields; PUT would clear the issue's other field values.
    path = "repos/{}/{}/issues/{}/issue-field-values".format(org, repo, issue_number)
    response = instance.post(path, {"issue_field_values": values})
    return response


def delete_issue_field_value(instance, org, repo, issue_number, field_id):
    path = "repos/{}/{}/issues/{}/issue-field-values/{}".format(org, repo, issue_number, field_id)
    return instance.delete(path)


def markdown_to_html(instance, text, context):
    # GitHub's own renderer, so GFM (tables, task lists, @mentions, #refs) matches what users see.
    # The vnd Accept type makes ASyncRestApi return the raw HTML instead of parsing JSON.
    response = instance.post("markdown", {"text": text, "mode": "gfm", "context": context},
                             accept_type="application/vnd.github+json")
    return response.decode() if isinstance(response, bytes) else response


def html_to_markdown(html):
    # Imported here so a missing html2text only affects the description, not the whole plugin.
    import html2text

    converter = html2text.HTML2Text()
    converter.body_width = 0
    return converter.handle(html).strip()


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
