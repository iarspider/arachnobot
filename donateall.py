import asyncio
import pathlib
from contextlib import suppress

import pygame
import requests
import json
from config import *
import datetime

def get_new_token():
    response = requests.post("https://www.donateall.online/public/api/v1/authenticate",
                             json={'username': music_login, 'password': music_password})

    if response.status_code == 200:
        with open('music_token.json', 'w') as f:
            f.write(response.text)
    else:
        print("Failed to get new music token: " + str(response.status_code) + " " + response.text)
        return None

    return response.json()


def refresh_token(token):
    response = requests.post("https://www.donateall.online/public/api/v1/refresh",
                             json={'refresh_token': token['refresh_token']})
    if response.status_code == 200:
        data = response.json()
        token['acess_token_expires'] = data['acess_token_expires']
        token['acess_token'] = data['acess_token']
        with open('music_token.json', 'w') as f:
            json.dump(token, f)
    else:
        print("Failed to refresh music token: " + str(response.status_code) + " " + response.text)
        token = None

    return token


def load_token():
    try:
        with open('music_token.json', 'r') as f:
            token = json.load(f)

        return token
    except (IOError, OSError, json.JSONDecodeError) as e:
        print("Failed to get token: " + str(e))
        return None


def login():
    token = load_token()
    if not token:
        token = get_new_token()
    else:
        refresh_expires = datetime.datetime.fromtimestamp(int(token['refresh_token_expires']) / 1000)
        access_expires = datetime.datetime.fromtimestamp(int(token['access_token_expires']) / 1000)
        now = datetime.datetime.now()
        if refresh_expires < now:
            token = get_new_token()
        else:
            if access_expires < now:
                token = refresh_token(token)

    return token


async def get_current_song(token):
    response = requests.get(# "https://www.donateall.online/public/api/v1/songs/queue",
                            "https://www.donateall.online/public/api/v1/songs/current",
                            headers={'Content-Type': 'application/json',
                                     'api_token': token['access_token']
                                     }
                            )
    print(response.text)


async def main():
    # setup_mixer()
    token = login()
    await get_current_song(token)
    # p = Periodic(get_current_song(token), time=5)
    # await p.start()
    # await asyncio.sleep(600)
    # await p.stop()
    # play_sound('matmatmat.mp3')
    # await asyncio.sleep(600)

if __name__ == '__main__':
    asyncio.run(main())
