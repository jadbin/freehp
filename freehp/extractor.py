# coding=utf-8

import re

from lxml import etree

ip_reg = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|\d{2,5})')


def is_ip(t):
    first = True
    for i in t.split('.'):
        if first:
            if int(i) == 0:
                return False
            first = False
        if int(i) > 255:
            return False
    return True


def is_port(t):
    t = int(t)
    # TODO HTTPS 443
    if t == 80:
        return True
    if 1024 < t < 65536:
        return True
    return False


def extract_proxies(html):
    try:
        root = etree.fromstring(html, parser=etree.HTMLParser())
        s = root.xpath('//body', smart_strings=False)
        text = ''
        for i in s:
            text += ' '.join(i.itertext())
    except Exception:
        return []
    res = []
    pre_ip = None
    for i in ip_reg.findall(text):
        if i.find('.') >= 0:
            pre_ip = i
        else:
            if pre_ip and is_ip(pre_ip) and is_port(i):
                res.append(pre_ip + ':' + i)
    return res
