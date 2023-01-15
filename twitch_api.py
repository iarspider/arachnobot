import os
import logging
import webbrowser

import json as simplejson
import requests
from requests_oauthlib import OAuth2Session

scope = [
    "channel:moderate",
    "chat:edit",
    "chat:read",
    "channel:read:redemptions",
    "channel:edit:commercial",
    "moderator:manage:banned_users",
]


def token_saver(token):
    with open("twitch_token.json", "w") as f:
        simplejson.dump(token, f)


def get_token(client_id, client_secret, redirect_uri):
    oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
    authorization_url, state = oauth.authorization_url(
        "https://id.twitch.tv/oauth2/authorize"
    )
    webbrowser.open_new(authorization_url)

    authorization_response = input("Enter the full callback URL: ").strip()
    token = oauth.fetch_token(
        "https://id.twitch.tv/oauth2/token",
        include_client_id=True,
        client_secret=client_secret,
        authorization_response=authorization_response,
        force_querystring=True,
    )

    token_saver(token)
    return token


def validate(oauth: OAuth2Session, can_refresh=True):
    try:
        r = requests.get(
            "https://id.twitch.tv/oauth2/validate",
            headers={"Authorization": f'OAuth {oauth.token["access_token"]}'},
        )
        # print(r.text)
        r.raise_for_status()
    except requests.HTTPError as e:
        if can_refresh:
            token = oauth.refresh_token(oauth.auto_refresh_url)
            token_saver(token)
            oauth_ = get_session(
                os.getenv('TWITCH_CLIENT_ID'),
                os.getenv('TWITCH_CLIENT_SECRET'),
                "https://iarazumov.com/oauth/twitch",
            )
            validate(oauth_, False)
        else:
            logging.fatal("Validation failed: " + str(e))
            raise RuntimeError("Validation failed")


def get_session(client_id, client_secret, redirect_uri):
    try:
        with open("twitch_token.json", "r") as f:
            token = simplejson.load(f)
    except (OSError, simplejson.JSONDecodeError, FileNotFoundError):
        print("Failed to load token!")
        token = get_token(client_id, client_secret, redirect_uri)

    oauth = OAuth2Session(
        client_id,
        token=token,
        auto_refresh_url="https://id.twitch.tv/oauth2/token",
        auto_refresh_kwargs={"client_id": client_id, "client_secret": client_secret},
        redirect_uri=redirect_uri,
        scope=scope,
        token_updater=token_saver,
    )

    validate(oauth)
    return oauth


def my_get_users(oauth, user_name):
    res = oauth.get(
        "https://api.twitch.tv/helix/users",
        params={"login": user_name},
        headers={"Client-ID": os.getenv('TWITCH_CLIENT_ID')},
    )
    try:
        res.raise_for_status()
    except requests.HTTPError:
        # print(res.text)
        exit(1)
    return res.json()["data"][0]


def main():
    import logging
    import http.client as http_client

    http_client.HTTPConnection.debuglevel = 1
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True

    oauth = get_session(
        os.getenv('TWITCH_CLIENT_ID'),
        os.getenv('TWITCH_CLIENT_SECRET'),
        "https://iarazumov.com/oauth/twitch",
    )
    validate(oauth)
    # print(my_get_users(oauth, "cwelth"))
    # print(my_get_users(oauth, "twitch"))
    my_id = my_get_users(oauth, "iarspider")["id"]
    #        params={"login": user_name},
    #        headers={"Client-ID": os.getenv('TWITCH_CLIENT_ID')},

    res = oauth.get(
        f"https://api.twitch.tv/helix/streams",
        params={"user_login": "iarspider"},
        headers={"Client-ID": os.getenv('TWITCH_CLIENT_ID')},
    )
    res.raise_for_status()
    from pprint import pprint

    pprint(res.json()["data"])


if __name__ == "__main__":
    main()
