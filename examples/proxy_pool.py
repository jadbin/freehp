# coding=utf-8

from random import randint

from freehp import ProxyPool
from freehp.errors import NoProxyAvailable

if __name__ == '__main__':
    pool = ProxyPool("http://localhost:8081")
    try:
        proxy = pool.get_proxy()
        print("The proxy is: {}".format(proxy))
    except NoProxyAvailable:
        print("No proxy available now")
    else:
        # connect the website using the proxy ...

        # ok is `True` if the connection succeeded, otherwise `False`
        ok = bool(randint(0, 1))
        print("Connection {}".format("succeeded" if ok else "failed"))
        # feed back the availability of the proxy
        pool.feed_back(proxy, ok)
