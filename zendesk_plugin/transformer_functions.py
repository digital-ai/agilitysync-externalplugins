import base64

import external_plugins.zendesk_plugin.default as DEFAULT
from agilitysync.external_lib.restapi import ASyncRestApi


def connect(instance_details):
    token = "Basic " + encode_to_base64_string(
        instance_details['email'],
        instance_details['password']
    )

    header = {
        'Authorization': token,
        'Content-Type': 'application/json',
        "Accept": "application/json",
    }

    return ASyncRestApi(instance_details['url'], headers=header)


def encode_to_base64_string(email, password):
    data = email + ":" + password
    data_bytes = data.encode('ascii')
    base64_bytes = base64.b64encode(data_bytes)
    return base64_bytes.decode("utf-8")


def check_connection(instance):
    instance_path = "organizations"

    path = "{}/{}/{}".format(
            DEFAULT.INITIAL_PATH,
            DEFAULT.REST_ENDPOINT_VERSION,
            instance_path)

    response = instance.get(path)

    if "organizations" in response:
        return "Connection to Zendesk server is successfull."
    else:
        return "Can not establish connection to Zendesk server."


def tickets(instance, id=None, payload=None):
    instance_path = "tickets/{}".format(id) if id else "tickets"
    path = "{}/{}/{}".format(
        DEFAULT.INITIAL_PATH,
        DEFAULT.REST_ENDPOINT_VERSION,
        instance_path)

    if payload:
        response = (instance.put(path, payload)
                    if id else instance.post(path, payload))
        return response["ticket"]
    else:
        response = instance.get(path)
        return response["tickets"]


def ticket_fields(instance, id=None, payload=None):
    instance_path = "ticket_fields/{}".format(id) if id else "ticket_fields"
    path = "{}/{}/{}".format(
        DEFAULT.INITIAL_PATH,
        DEFAULT.REST_ENDPOINT_VERSION,
        instance_path)

    if payload:
        if id:
            response = instance.put(path, payload)
        else:
            response = instance.post(path, payload)
        return response["ticket_field"]
    else:
        response = instance.get(path)
        return response["ticket_fields"]


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
