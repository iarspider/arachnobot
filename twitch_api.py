# import re
# from config import *
# import requests
# # cid = "lwa3aygjk7zxej6yenpo4x0qmj971a"
# uri = "http://localhost/oauth"
# scopes = ["channel:moderate", "chat:edit", "chat:read", "channel:read:redemptions"]
#
# url = "https://id.twitch.tv/oauth2/authorize" \
#       "?client_id={cid}" \
#       "&redirect_uri={uri}" \
#       "&response_type=code" \
#       "&scope={scope}"
#
# url2 = "https://id.twitch.tv/oauth2/token" \
#     "?client_id={cid}" \
#     "&client_secret={secret}" \
#     "&code={code}" \
#     "&grant_type=authorization_code" \
#     "&redirect_uri={uri}"
#
# if __name__ == '__main__':
#     print("open this link please: ", url.format(cid=twitch_client_id, uri=uri, scope="+".join(scopes)))
#     url = input("Please enter redirect URL or code")
#     if 'code' in url:
#         code = re.search('code=([a-f0-9]+)', url)
#         if code:
#             code = code.group(1)
#     else:
#         code = url
#
#     res = requests.post(url2.format(cid=twitch_client_id, uri=uri, code=code, secret=twitch_client_secret)
#     print(res.json)
import logging
import webbrowser

import simplejson
import requests
from requests_oauthlib import OAuth2Session

import config


def token_saver(token):
    with open("twitch_token.json", "w") as f:
        simplejson.dump(token, f)


def get_token(client_id, client_secret, redirect_uri):
    scope = ["channel:moderate", "chat:edit", "chat:read", "channel:read:redemptions"]
    oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
    authorization_url, state = oauth.authorization_url("https://id.twitch.tv/oauth2/authorize")
    # print('Please go to\n %s\n and authorize access.' % authorization_url)
    webbrowser.open_new(authorization_url)

    authorization_response = input('Enter the full callback URL').strip()
    token = oauth.fetch_token("https://id.twitch.tv/oauth2/token", client_id=client_id, client_secret=client_secret,
                              authorization_response=authorization_response, force_querystring=True,
                              include_client_id=True)

    token_saver(token)
    return token


def get_session(client_id, client_secret, redirect_uri):
    try:
        f = open("twitch_token.json", 'r')
        token = simplejson.load(f)
    except (OSError, simplejson.JSONDecodeError, FileNotFoundError):
        print("Failed to load token!")
        token = get_token(client_id, client_secret, redirect_uri)

    scope = ["channel:moderate", "chat:edit", "chat:read", "channel:read:redemptions"]
    oauth = OAuth2Session(client_id, token=token, auto_refresh_url="https://id.twitch.tv/oauth2/token",
                          auto_refresh_kwargs={'client_id': client_id, 'client_secret': client_secret},
                          redirect_uri=redirect_uri, scope=scope, token_updater=token_saver)

    try:
        oauth.get('https://id.twitch.tv/oauth2/validate')
    except requests.HTTPError as e:
        logging.fatal("Validation failed: " + str(e))
        raise RuntimeError("Validation failed")

    return oauth


def main():
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

    get_session(config.twitch_client_id, config.twitch_client_secret, 'https://iarazumov.com/oauth/twitch')


if __name__ == '__main__':
    main()
