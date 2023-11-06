import base64

from external_plugins.gitlab import default as DEFAULT
from agilitysync.external_lib.restapi import ASyncRestApi

fields = [
    {
        "required": True,
        "disabled field": False,
        "customfield": False,
        "raw_title": "title",
        "title": "title",
        "type": "title",
        "IsMultivalue": False
    },
    {
        "required": False,
        "disabled field": False,
        "customfield": False,
        "raw_title": "description",
        "title": "description",
        "type": "description",
        "IsMultivalue": False
    },
    {
        "required": False,
        "disabled field": False,
        "customfield": False,
        "raw_title": "labels",
        "title": "labels",
        "type": "labels",
        "IsMultivalue": True
    },
    {
        "required": False,
        "disabled field": False,
        "customfield": False,
        "raw_title": "weight",
        "title": "weight",
        "type": "weight",
        "IsMultivalue": False
    },

]
fields_epic = [
    {
        "required": True,
        "disabled field": False,
        "customfield": False,
        "raw_title": "title",
        "title": "title",
        "type": "title",
        "IsMultivalue": False
    },
    {
        "required": False,
        "disabled field": False,
        "customfield": False,
        "raw_title": "description",
        "title": "description",
        "type": "description",
        "IsMultivalue": False
    },

    {
        "required": False,
        "disabled field": False,
        "customfield": False,
        "raw_title": "labels",
        "title": "labels",
        "type": "labels",
        "IsMultivalue": True
    },

    # {
    #     "required": False,
    #     "disabled field": False,
    #     "customfield": False,
    #     "raw_title": "color",
    #     "title": "color",
    #     "type": "color",
    #     "IsMultivalue" : True
    # },
    {
        "required": False,
        "disabled field": False,
        "customfield": False,
        "raw_title": "confidential",
        "title": "confidential",
        "type": "confidential",
        "IsMultivalue": False
    },
    {
        "required": False,
        "disabled field": False,
        "customfield": False,
        "raw_title": "start_date_fixed",
        "title": "start_date_fixed",
        "type": "start_date_fixed",
        "IsMultivalue": False
    },
    {
        "required": False,
        "disabled field": False,
        "customfield": False,
        "raw_title": "due_date_fixed",
        "title": "due_date_fixed",
        "type": "due_date_fixed",
        "IsMultivalue": False
    },

]

BOOLEAN_VALUES = [
    {'id': 'True', 'value': 'True', 'display_value': 'True'},
    {'id': 'False', 'value': 'False', 'display_value': 'False'},
]


def ticfields():
    return fields


def get_issue(instance, proj_id, workid):
    path = "{}/{}/{}/{}".format("projects", proj_id["project"], "issues", workid)

    return instance.get(path)


def epicfields():
    return fields_epic


def connect(instance_details):
    return ASyncRestApi(instance_details['url'], headers={
        "authorization": "Bearer {}".format(instance_details["token"]),
        "Accept": "application/json",
        "Content-Type": "application/json"
    })


def check_connection(instance, instance_details):
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


def get_org_child(instance, parent_id):
    instance_path = "groups"
    path = "{}".format(
        instance_path,
        parent_id,
        "subgroups")
    response = instance.get(path)
    return response


def get_repos(instance, details):
    instance_path = "projects"
    path = "{}/{}/{}".format(
        "groups",
        details,
        instance_path)
    response = instance.get(path)
    return response


def tickets(instance, payload, id, name, parentid=None):
    orgsplit = id.split('/')

    if name == "No Project":
        if parentid[0] is not None:
            path = "{}/{}/{}".format(
                "groups",
                orgsplit[0],
                "epics"
            )
            res = instance.post(path, payload)

            path = "{}/{}/{}/{}/{}/{}".format(
                "groups",
                orgsplit[0],
                "epics", parentid[1], "epics", res['id']
            )
            return instance.post(path)
        else:
            path = "{}/{}/{}".format(
                "groups",
                orgsplit[0],
                "epics",
            )


    else:
        path = "{}/{}/{}".format(
            "projects",
            orgsplit[0],
            "issues"
        )

    if payload:
        response = instance.post(path, payload)

        return response
    else:
        response = instance.get(path)
        return response


def update_tickets(instance, payload, id, name, parentid=None, workid=None):
    orgsplit = id.split('/')

    if name == "No Project":
        if parentid[0] is not None and len(payload) != 0:
            path = "{}/{}/{}/{}".format(
                "groups",
                orgsplit[0],
                "epics", workid
            )
            res = instance.put(path, payload)

            path = "{}/{}/{}/{}/{}/{}".format(
                "groups",
                orgsplit[0],
                "epics", parentid[1], "epics", res['id']
            )
            return instance.post(path)
        elif parentid[0] is not None:
            path = "{}/{}/{}/{}".format(
                "groups",
                orgsplit[0],
                "epics", workid
            )
            res = instance.get(path)

            path = "{}/{}/{}/{}/{}/{}".format(
                "groups",
                orgsplit[0],
                "epics", parentid[1], "epics", res['id']
            )
            return instance.post(path)


        else:
            path = "{}/{}/{}/{}".format(
                "groups",
                orgsplit[0],
                "epics", workid
            )


    else:
        path = "{}/{}/{}/{}".format(
            "projects",
            orgsplit[0],
            "issues", workid
        )

    if payload:
        response = instance.put(path, payload)

        return response
    else:
        response = instance.get(path)
        return response


def ticket_fields(instance, id=None, payload=None):
    tickets = [
        {
            'asset': "issues",
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
    path = "{}/{}/{}".format(
        "projects",
        id,
        instance_path)

    if payload:
        response = instance.post(path, payload)
        return response
    else:
        response = instance.get(path)
        return response


def get_fields_values(instance, field):
    path = "{}/{}"


def get_org_id(instance, id):
    path = "{}/{}".format("projects", id)

    response = instance.get(path)
    return response["namespace"]["id"]


def get_parent_id(proj_id, iid, instance):
    path = "{}/{}/{}/{}".format("projects", proj_id, "issues", iid)

    try:
        response = instance.get(path)
        return response
    except:
        return response["error"]
