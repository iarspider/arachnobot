from dotenv import load_dotenv
from loguru import logger

load_dotenv()

import json
import os
import uuid
import webbrowser

from requests_oauthlib import OAuth2Session


def token_saver(token):
    with open("nightbot_token.json", "w") as f:
        json.dump(token, f)


def random_state():
    return "".join(str(uuid.uuid4()).split("-"))


def get_token(client_id, client_secret, redirect_uri):
    scope = [
        "timers",
        "commands",
    ]
    oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
    state = random_state()
    authorization_url, state = oauth.authorization_url(
        "https://api.nightbot.tv/oauth2/authorize",
        state=state,
    )
    # print('Please go to\n %s\n and authorize access.' % authorization_url)
    webbrowser.open(authorization_url)
    print("Please authorize...")

    authorization_response = input("Enter the full callback URL").strip()
    token = oauth.fetch_token(
        "https://api.nightbot.tv/oauth2/token",
        client_id=client_id,
        client_secret=client_secret,
        authorization_response=authorization_response,
    )

    token_saver(token)
    return token


def get_nightbot_session(client_id, client_secret, redirect_uri):
    try:
        f = open("nightbot_token.json", "r")
        token = json.load(f)
    except (OSError, FileNotFoundError, json.JSONDecodeError):
        print("Failed to load token!")
        token = get_token(client_id, client_secret, redirect_uri)

    scope = [
        "timers",
    ]
    oauth = OAuth2Session(
        client_id,
        token=token,
        auto_refresh_url="https://api.nightbot.tv/oauth2/token",
        auto_refresh_kwargs={"client_id": client_id, "client_secret": client_secret},
        redirect_uri=redirect_uri,
        scope=scope,
        token_updater=token_saver,
    )

    return oauth


def get_timers(oauth):
    r = oauth.get("https://api.nightbot.tv/1/timers")
    r.raise_for_status()
    return r.json().get("timers", [])


def get_commands(oauth):
    r = oauth.get("https://api.nightbot.tv/1/commands")
    r.raise_for_status()
    return r.json().get("commands", [])


def get_command(oauth, id):
    r = oauth.get(f"https://api.nightbot.tv/1/commands/{id}")
    r.raise_for_status()
    return r.json().get("command", None)


def put_command(oauth, id, data):
    r = oauth.put(
        f"https://api.nightbot.tv/1/commands/{id}",
        data=json.dumps(data),
        headers={"Content-Type": "application/json"},
    )


def enable_disable_timer(oauth, name, state):
    logger.info(f"Setting timer's {name} state to {state}")
    timers = get_timers(oauth)
    timer = [x for x in timers if x["name"] == name]
    if len(timer) < 1:
        logger.error(f"No such timer: {name}")
        return
    if len(timer) > 1:
        logger.error(f"Multiple timers with name {name}")
        return

    timer = timer[0]

    timer["enabled"] = state
    del timer["createdAt"]
    del timer["updatedAt"]
    del timer["nextRunAt"]

    r = oauth.put(
        f"https://api.nightbot.tv/1/timers/{timer['_id']}",
        data=json.dumps(timer),
        headers={"Content-Type": "application/json"},
    )

    r.raise_for_status()
    logger.info(f"Timer state changed successfully")


def enable_timer(oauth, name):
    enable_disable_timer(oauth, name, True)


def disable_timer(oauth, name):
    enable_disable_timer(oauth, name, False)


def main():
    from config import (
        nightbot_redirect_url,
    )
    import logging

    try:
        import http.client as http_client
    except ImportError:
        # Python 2
        # noinspection PyUnresolvedReferences
        import httplib as http_client

    http_client.HTTPConnection.debuglevel = 1
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
    oauth = get_nightbot_session(
        os.getenv("NIGHTBOT_CLIENT_ID"),
        os.getenv("NIGHTBOT_CLIENT_SECRET"),
        nightbot_redirect_url,
    )

    enable_timer(oauth, "Мультитвич")
    print(get_timers(oauth))

    disable_timer(oauth, "Мультитвич")
    print(get_timers(oauth))


if __name__ == "__main__":
    # Monkey-patching
    main()
