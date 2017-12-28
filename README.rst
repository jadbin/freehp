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

Use pip:

.. code-block:: bash

    $ pip install freehp

Getting Started
===============

Run proxy agent:

.. code-block:: bash

    $ freehp run

The proxy agent by default runs on port ``8081``.
Then we can visit http://localhost:8081/ and see a list of latest available proxies.

Requirements
============

- Python >= 3.5
- `aiohttp`_

.. _aiohttp: https://pypi.python.org/pypi/aiohttp
