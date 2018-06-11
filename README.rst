======
FreeHP
======

.. image:: https://img.shields.io/badge/license-Apache 2-blue.svg
    :target: https://github.com/jadbin/freehp/blob/master/LICENSE


Key Features
============

- Providing free HTTP proxies.

Installation
============

Use pip::

    $ pip install freehp

Getting Started
===============

We need prepare a configuration file like ``conf/config.py``, then run FreeHP::

    $ freehp run -c conf/config.py

FreeHP by default runs on port ``6256``.
Thus we can visit http://localhost:6256/proxies and see a list of latest available proxies.

Requirements
============

- Python >= 3.5.3
- `aiohttp`_
- `lxml`_

.. _aiohttp: https://pypi.python.org/pypi/aiohttp
.. _lxml: https://pypi.python.org/pypi/lxml
