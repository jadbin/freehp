# coding=utf-8

from freehp import SimpleProxyPool
from freehp.errors import NoProxyAvailable

if __name__ == '__main__':
    pool = SimpleProxyPool("http://localhost:8081")
    try:
        proxy = pool.get_proxy()
        print("The proxy is: {}".format(proxy))
    except NoProxyAvailable:
        print("No proxy available now")
