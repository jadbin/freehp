======
FreeHP
======

.. image:: https://img.shields.io/badge/license-Apache 2-blue.svg
    :target: https://github.com/jadbin/freehp/blob/master/LICENSE


Key Features
============

- Provides proxy agent (server) to scrap free HTTP proxies and verify the usability of each of them.
- Provides proxy pool (client) to collect the proxies from agent and maintains them locally.


Installation
============

Use pip:

.. code-block:: bash

    $ pip install freehp

Use source code:

.. code-block:: bash

    $ python setup.py install


Getting Started
===============

Proxy Agent
-----------

Run proxy agent:

.. code-block:: bash

    $ freehp run

The proxy agent by default runs on port ``8081``.
Then we can visit http://localhost:8081/ and see a list of latest available proxies.

Proxy Pool
----------

An usage example of ``SimpleProxyPool``:

.. code-block:: python

    from freehp import SimpleProxyPool
    from freehp.errors import NoProxyAvailable

    if __name__ == '__main__':
        pool = SimpleProxyPool("http://localhost:8081")
        try:
            proxy = pool.get_proxy()
            print("The proxy is: {}".format(proxy))
        except NoProxyAvailable:
            print("No proxy available now")

``SimpleProxyPool`` randomly selects the proxy in the list each time.

An usage example of ``ProxyPool``:

.. code-block:: python

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

``ProxyPool`` prefers to select the proxy with high connection success rate.

Requirements
============

- Python >= 3.5
- `aiohttp`_
- `pyyaml`_

.. _aiohttp: https://pypi.python.org/pypi/aiohttp
.. _pyyaml: https://pypi.python.org/pypi/pyyaml
