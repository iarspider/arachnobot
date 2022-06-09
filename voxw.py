import time

import requests
from bs4 import BeautifulSoup

import re


def get_filename_from_cd(cd):
    """
    Get filename from content-disposition
    """
    if not cd:
        return None
    fname = re.findall('filename=(.+)', cd)
    if len(fname) == 0:
        return None
    return fname[0]


def main():
    session = requests.Session()
    res = session.get('https://voxworker.com/ru')
    res.raise_for_status()

    soup = BeautifulSoup(res.text, 'html.parser')
    # with open(r'e:\temp\vox.htm', 'r', encoding='utf-8') as f:
    #     soup = BeautifulSoup(f.read(), 'html.parser')

    textId = soup.select("input[name=textId]")
    sessionId = soup.select("input[name=sessionId]")

    data = dict(textId=textId[0]['value'],
                sessionId=sessionId[0]['value'],
                voice='ya-zahar',
                speed='1.0',
                pitch='1.0',
                text='Вы можете менять ударение знаком плюс. Например: хлоп+ок в ладоши или белый хл+опок.'
                )

    res = session.post('https://voxworker.com/ru/ajax/convert', data=data)
    res.raise_for_status()
    resj = res.json()
    if resj['status'] == 'notify':
        print(f"FAIL: {resj['error']}, {resj['errorText']}")
        return

    statusAttemptCount = 0
    while statusAttemptCount < 60 and resj['status'] == 'queue':
        res = session.get(f'https://voxworker.com/ru/ajax/status?id={resj["taskId"]}')
        res.raise_for_status()
        resj = res.json()
        statusAttemptCount += 1
        time.sleep(1)

    if statusAttemptCount == 60:
        print('[FAIL] Conversion error')
        return

    if resj['status'] != 'ok':
        print(f"FAIL: {resj['error']}, {resj['errorText']}")
        return

    if resj['status'] == 'ok':
        print(resj['downloadUrl'])

        res = session.get(resj['downloadUrl'])
        res.raise_for_status()
        filename = get_filename_from_cd(res.headers.get('content-disposition'))
        open(filename.strip('"'), 'wb').write(res.content)


if __name__ == '__main__':
    main()
