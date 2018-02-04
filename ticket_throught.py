#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import requests
from bs4 import BeautifulSoup
import re
import json
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager
import ssl
import logging
import string
import browsercookie
import os
import shutil
import time
from PIL import Image
import datetime

# ===========================  Setting  ===========================
TARGET_SHOW = 1
TARGET_AREAS = [u'C區']

BUY_TICKET_NUMBER = 1

# ===========================  Use Info  ===========================
USER_AGENT_INFO = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_3) ' + \
                  'AppleWebKit/537.36 (KHTML, like Gecko) ' + \
                  'Chrome/63.0.3239.132 ' + \
                  'Safari/537.36'

# ==================================================================
logging.basicConfig(level=logging.DEBUG)
logging.getLogger().setLevel(logging.INFO)


RETRY_CAPTUA_TIME = 5
ENCODE_CHARSET = 'utf-8'

HTML_FOLDER = 'data'
CAPTUA_DIR_PATH = 'captua'
CAPTUA_DICT_FILE = 'captua/dict.json'
DEBUG_FLAG = False

REQUEST_HEADER_BASE = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Pragma': 'no-cache',
    'Upgrade-Insecure-Requests': 1,
    'User-Agent': USER_AGENT_INFO,
}


class ForceTLSV1Adapter(HTTPAdapter):
    """Require TLSv1 for the connection"""
    def init_poolmanager(self, connections, maxsize, block=False):
        # This method gets called when there's no proxy.
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_version=ssl.PROTOCOL_TLSv1,
        )

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        # This method is called when there is a proxy.
        proxy_kwargs['ssl_version'] = ssl.PROTOCOL_TLSv1
        return super(ForceTLSV1Adapter, self).proxy_manager_for(proxy, **proxy_kwargs)


def GetCookie(website_url, cookie_path):
    myNeedDomainDict = {}
    targetDomain = website_url.split('/')[-1]
    for _ in browsercookie.chrome([cookie_path]):
        if targetDomain in _.domain:
            myNeedDomainDict[_.name] = _.value
    return myNeedDomainDict


def URLToFileName(url):
    text = string.replace(url, '/', '_')
    return string.replace(text, ':', '_')


def ShowRequestGetTicketURL(website_url, show_url, session):
    header = {k: v for k, v in REQUEST_HEADER_BASE.items()}
    header.update({
        'Host': website_url.split('/')[-1],
        'Referer': website_url
    })
    r = session.get(show_url, headers=header)
    if DEBUG_FLAG:
        logging.warning(r.text.encode(ENCODE_CHARSET))
    logging.info('Show url: {0}'.format(r.url))
    with open('{0}/{1}.html'
              .format(HTML_FOLDER, URLToFileName(show_url)), 'w+') as f:
        f.write(r.text.encode(ENCODE_CHARSET))
    if u'登入' in r.text:
        logging.error(r.text.encode(ENCODE_CHARSET))
        raise IOError('fail')
    soup = BeautifulSoup(r.text, 'html.parser')
    trs = soup.select('tbody tr')
    if TARGET_SHOW > len(trs):
        target = 0
    else:
        target = TARGET_SHOW - 1
    return website_url + trs[target].select('input')[0]['data-href']


def CheckRemaingTicket(areaSeat):
    remainingReKey = u'剩餘 ([0-9]+)'
    foundRemains = re.findall(r'' + remainingReKey, areaSeat)
    if 0 == len(foundRemains):
        return True
    if int(foundRemains[0]) < BUY_TICKET_NUMBER:
        return False
    return True


def CalculateTargetArea(length):
    return int(length / 3 * 2)


def TicketRequestGetBuyURL(website_url, ticket_url, session):
    header = {k: v for k, v in REQUEST_HEADER_BASE.items()}
    header.update({
        'Host': website_url.split('/')[-1],
        'Referer': website_url
    })
    r = session.get(ticket_url, headers=header)
    if DEBUG_FLAG:
        logging.warning(r.text.encode(ENCODE_CHARSET))
    if u'登入' in r.text:
        logging.error(r.text.encode(ENCODE_CHARSET))
        raise IOError('fail')
    logging.info('Ticket url: {0}'.format(r.url))
    with open('{0}/{1}.html'
              .format(HTML_FOLDER, URLToFileName(ticket_url)), 'w+') as f:
        f.write(r.text.encode(ENCODE_CHARSET))
    areaURLList = re.findall(r'var areaUrlList = (.*);', r.text)
    areaID2URLDict = json.loads(areaURLList[0])

    soup = BeautifulSoup(r.text, 'html.parser')
    areaSeat2IDDict = dict([(soup.select('#' + areaID)[0].text, areaID)
                            for areaID in areaID2URLDict.keys()])
    foundAreaIDs = []
    for targetArea in TARGET_AREAS:
        foundAreaIDs = [(targetArea, areaSeat2IDDict[areaSeat])
                        for areaSeat in areaSeat2IDDict.keys()
                        if targetArea in areaSeat and CheckRemaingTicket(areaSeat)]
        if 0 < len(foundAreaIDs):
            break

    if 0 < len(foundAreaIDs):
        logging.info('Area: {0}'.format(foundAreaIDs[0][0].encode(ENCODE_CHARSET)))
        subURL = areaID2URLDict[foundAreaIDs[0][1]]
        return website_url + subURL

    # Get one with remaining ticket
    # areaList = sorted(areaID2URLDict.items(), key=lambda x: int(x[0].split('_')[1]))
    areaIDs = [(areaSet, areaSeat2IDDict[areaSeat])
               for areaSet in areaSeat2IDDict.keys()
               if CheckRemaingTicket(areaSeat)]
    if 0 == len(areaIDs):
        raise IOError('There is no ticket for {0} here, see {1} for checking'.format(
                      BUY_TICKET_NUMBER,
                      '{0}/{1}.html'.format(HTML_FOLDER, URLToFileName(ticket_url))
                      ))
    idx = CalculateTargetArea(len(areaIDs))
    subURL = areaID2URLDict[areaIDs[idx][1]]
    logging.info('Area: {0}'.format(areaIDs[idx][0].encode(ENCODE_CHARSET)))
    return website_url + subURL


def GetCaptuaData(session, website_url, soup):
    captua_div = soup.select('div.mTop')

    if 0 == len(captua_div):
        return False, None
    img_src = website_url + captua_div[0].select('img#yw0')[0]['src']

    header = {k: v for k, v in REQUEST_HEADER_BASE.items()}
    header.update({
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Host': website_url.split('/')[-1],
        'Referer': website_url
    })

    r = session.get(img_src, stream=True, headers=header)
    image_name = '{0}.png'.format(datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    image_path = os.path.join(CAPTUA_DIR_PATH, image_name)

    with open(image_path, 'wb') as f:
        shutil.copyfileobj(r.raw, f)

    logging.info(image_path)
    Image.open(image_path).show()
    value = raw_input('Enter capcha image.... \n')

    os.remove(image_path)
    return True, value


def BuyRequestGetOrderURL(website_url, buy_url, session):
    header = {k: v for k, v in REQUEST_HEADER_BASE.items()}
    header.update({
        'Host': website_url.split('/')[-1],
        'Referer': website_url
    })
    r = session.get(buy_url, headers=header)
    if DEBUG_FLAG:
        logging.warning(r.text.encode(ENCODE_CHARSET))
    if u'登入' in r.text:
        logging.error(r.text.encode(ENCODE_CHARSET))
        raise IOError('fail')
    logging.info('Buy url: {0}'.format(r.url))
    with open('{0}/{1}_get.html'
              .format(HTML_FOLDER, URLToFileName(buy_url)), 'w+') as f:
        f.write(r.text.encode(ENCODE_CHARSET))
    soup = BeautifulSoup(r.text, 'html.parser')
    forms = soup.select('form')
    formData = {'TicketForm[agree]': 1}
    for formInput in forms[0].select('input'):
        if 'id' not in formInput.attrs:
            continue
        if formInput['id'] != 'CSRFTOKEN' and \
           formInput['id'] != 'ticketPriceSubmit':
            continue
        formData[formInput['name']] = formInput['value']

    for selectInput in forms[0].select('select'):
        if 'TicketForm' not in selectInput['name']:
            continue
        formData[selectInput['name']] = BUY_TICKET_NUMBER

    captua_found, captua_value = GetCaptuaData(session, website_url, soup)

    if captua_found:
        for formInput in forms[0].select('input'):
            if 'id' not in formInput.attrs:
                continue
            if formInput['id'] != 'TicketForm_verifyCode':
                continue
            formData[formInput['name']] = captua_value
            break

    logging.info(formData)
    header = {k: v for k, v in REQUEST_HEADER_BASE.items()}
    header.update({
        'Host': website_url.split('/')[-1],
        'Content-Length': 251,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': website_url,
        'Referer': buy_url
    })
    r = session.post(r.url, data=formData, headers=header)
    if DEBUG_FLAG:
        logging.warning(r.text.encode(ENCODE_CHARSET))
    with open('{0}/{1}_post.html'
              .format(HTML_FOLDER, URLToFileName(r.url)), 'w+') as f:
        f.write(r.text.encode(ENCODE_CHARSET))

    logging.info(r.url)
    logging.info('----')
    if r.history:
        for resp in r.history:
            logging.info('history status: {0}, url {1}'.format(resp.status_code, resp.url))
        logging.info('history status: {0}, url {1}'.format(r.status_code, r.url))
    return r.url


def GetAlertError(message):
    alertKey = u'alert\(\"(.*?)\"\)'
    foundAlert = re.findall(r'' + alertKey, message)
    return foundAlert[0].decode('unicode-escape')


def CheckRequest(website_url, order_url, session):
    header = {k: v for k, v in REQUEST_HEADER_BASE.items()}
    header.update({
        'Host': website_url.split('/')[-1],
        'Referer': website_url
    })

    r = session.get(order_url, headers=header)
    if DEBUG_FLAG:
        logging.warning(r.text.encode(ENCODE_CHARSET))
    if u'登入' in r.text:
        logging.error(r.text.encode(ENCODE_CHARSET))
        raise IOError('fail')
    logging.info('Order url: {0}'.format(r.url))
    with open('{0}/{1}_get.html'.format(HTML_FOLDER, URLToFileName(order_url)), 'w+') as f:
        f.write(r.text.encode(ENCODE_CHARSET))
    data = json.loads(r.text)
    if 'alert' in data['message']:
        alertMsg = GetAlertError(data['message'])
        logging.error(alertMsg)
        raise IOError('There have alert!!!')
    return data['message']


def go_try_ticket(website_url, show_url, order_url, cookie_path):
    if not os.path.exists(HTML_FOLDER):
        os.mkdir(HTML_FOLDER)
    if not os.path.isdir(HTML_FOLDER):
        raise IOError('{0} not dir'.format(HTML_FOLDER))
    if not os.path.exists(CAPTUA_DIR_PATH):
        os.mkdir(CAPTUA_DIR_PATH)
    if not os.path.isdir(CAPTUA_DIR_PATH):
        raise IOError('{0} not dir'.format(CAPTUA_DIR_PATH))
    if 0 >= TARGET_SHOW:
        raise IOError('Wrong setting: TARGET_SHOW: {0}'.format(TARGET_SHOW))
    if 0 >= TARGET_AREAS:
        raise IOError('Wrong setting: TARGET_AREAS: {0}'.format(TARGET_AREAS))
    with requests.Session() as s:
        s.mount(website_url, ForceTLSV1Adapter())
        s.cookies = requests.utils.cookiejar_from_dict(GetCookie(website_url, cookie_path))
        ticket_url = ShowRequestGetTicketURL(website_url, show_url, s)
        buy_url = TicketRequestGetBuyURL(website_url, ticket_url, s)
        for _ in range(1, RETRY_CAPTUA_TIME):
            check_url = BuyRequestGetOrderURL(website_url, buy_url, s)
            if check_url != buy_url:
                break

        # After buying ticket, need send below request for record it

        msg = CheckRequest(website_url, order_url, s)
        while 1:
            logging.info(msg.encode(ENCODE_CHARSET))
            if u'結帳' in msg:
                break
            time.sleep(0.1)
            msg = CheckRequest(website_url, order_url, s)

        logging.info('\n\n\n')
        logging.info('----------------------------------------------------------------------')
        logging.info('I\'m Finish')
        logging.info('Let\'s goto {0} to check ticket'.format(order_url))


def parse_arguement():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--target',
                        help='enter the target website',
                        type=str,
                        required=True)
    parser.add_argument('-s', '--show',
                        help='enter the target show',
                        type=str,
                        required=True)
    parser.add_argument('-o', '--order',
                        help='enter the order url',
                        type=str,
                        required=True)
    parser.add_argument('-c', '--cookie_path',
                        help='enter the cookie position',
                        type=str,
                        required=True)

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_arguement()
    website_url = args.target
    show_url = args.show
    order_url = args.order
    cookie_position = args.cookie_path

    go_try_ticket(website_url, show_url, order_url, cookie_position)
