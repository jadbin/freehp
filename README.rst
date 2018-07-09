======
freehp
======

.. image:: https://travis-ci.org/jadbin/freehp.svg?branch=master
    :target: https://travis-ci.org/jadbin/freehp

.. image:: https://coveralls.io/repos/github/jadbin/freehp/badge.svg?branch=master
    :target: https://coveralls.io/github/jadbin/freehp?branch=master

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

We need prepare a configuration file like ``conf/config.py``, then run freehp::

    $ freehp run -c conf/config.py

By default, freehp runs on port ``6256``.
Thus we can visit http://localhost:6256/proxies and see a list of latest available proxies.

Requirements
============

- Python >= 3.5.3
- `aiohttp`_
- `lxml`_

.. _aiohttp: https://pypi.python.org/pypi/aiohttp
.. _lxml: https://pypi.python.org/pypi/lxml
