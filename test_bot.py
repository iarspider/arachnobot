import asyncio
import logging
import webbrowser
from typing import List

try:
    import json as json
except ImportError:
    import json

import requests
from requests_oauthlib import OAuth2Session
from twitchio import Channel, User, Client
from twitchio.ext import commands, pubsub
from config import *

scope = ["channel:moderate", "chat:edit", "chat:read", "channel:read:redemptions", "channel:edit:commercial"]


def token_saver(token):
    with open("twitch_token.json", "w") as f:
        json.dump(token, f)


def validate(oauth: OAuth2Session, can_refresh=True):
    try:
        r = requests.get('https://id.twitch.tv/oauth2/validate',
                         headers={'Authorization': f'OAuth {oauth.token["access_token"]}'})
        # print(r.text)
        r.raise_for_status()
    except requests.HTTPError as e:
        if can_refresh:
            token = oauth.refresh_token(oauth.auto_refresh_url)
            token_saver(token)
            oauth_ = get_session(twitch_client_id, twitch_client_secret,
                                 'https://iarazumov.com/oauth/twitch')
            validate(oauth_, False)
        else:
            logging.fatal("Validation failed: " + str(e))
            raise RuntimeError("Validation failed")


def get_token(client_id, client_secret, redirect_uri):
    oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
    authorization_url, state = oauth.authorization_url("https://id.twitch.tv/oauth2/authorize")
    webbrowser.open_new(authorization_url)

    authorization_response = input('Enter the full callback URL: ').strip()
    token = oauth.fetch_token("https://id.twitch.tv/oauth2/token", include_client_id=True, client_secret=client_secret,
                              authorization_response=authorization_response, force_querystring=True)

    token_saver(token)
    return token


def get_session(client_id, client_secret, redirect_uri):
    try:
        with open("twitch_token.json", 'r') as f:
            token = json.load(f)
    except (OSError, json.JSONDecodeError, FileNotFoundError):
        print("Failed to load token!")
        token = get_token(client_id, client_secret, redirect_uri)

    oauth = OAuth2Session(client_id, token=token, auto_refresh_url="https://id.twitch.tv/oauth2/token",
                          auto_refresh_kwargs={'client_id': client_id, 'client_secret': client_secret},
                          redirect_uri=redirect_uri, scope=scope, token_updater=token_saver)

    validate(oauth)
    return oauth


class Bot(commands.Bot):

    def __init__(self):
        # Initialise our Bot with our access token, prefix and a list of channels to join on boot...
        # prefix can be a callable, which returns a list of strings or a string...
        # initial_channels can also be a callable which returns a list of strings...
        super().__init__(token=twitch_chat_password, prefix='?', initial_channels=['#iarspider'])

        self.pubsub_sess = get_session(twitch_client_id, twitch_client_secret, twitch_redirect_url)

        self.pubsub_client = Client(token=self.pubsub_sess.token['access_token'].replace('oauth2:', ''),
                                    initial_channels=['#iarspider'],
                                    client_secret=twitch_client_secret)
        self.pubsub_client.pubsub = pubsub.PubSubPool(self.pubsub_client)

    async def event_ready(self):
        # Notify us when everything is ready!
        # We are logged in and ready to chat and use commands...
        c: Channel = self.connected_channels[0]
        u: List["User"] = await self.fetch_users(names=[c.name])
        uu: User = u[0]
        print(f'User {c.name} has id {uu.id}')
        print(f'Logged in as | {self.nick}')

        topics = [pubsub.channel_points(self.pubsub_client._http.token)[uu.id]]
        # noinspection PyUnresolvedReferences
        await self.pubsub_client.pubsub.subscribe_topics(topics)
        asyncio.ensure_future(self.pubsub_client.start())

    @commands.command()
    async def hello(self, ctx: commands.Context):
        # Here we have a command hello, we can invoke our command with our prefix and command name
        # e.g ?hello
        # We can also give our commands aliases (different names) to invoke with.

        # Send a hello back!
        # Sending a reply back to the channel is easy... Below is an example.
        await ctx.send(f'Hello {ctx.author.name}!')


if __name__ == '__main__':
    bot = Bot()
    bot.run()
