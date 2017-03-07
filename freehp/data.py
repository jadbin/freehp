# coding=utf-8

from os import makedirs
from os.path import dirname, abspath, exists
import logging
import sqlite3
import json

log = logging.getLogger(__name__)


class ProxyDb:
    commit_count = 1000

    def __init__(self, db_file):
        db_file = abspath(db_file)
        log.debug("Load proxy database '{0}'".format(db_file))
        db_dir = dirname(db_file)
        if not exists(db_dir):
            makedirs(db_dir, mode=0o775)
        self._conn = sqlite3.connect(db_file, check_same_thread=False)
        self._update_count = 0

    def create_table(self, tbl_name):
        self.drop_table(tbl_name)
        self._conn.execute("""CREATE TABLE {} (
              addr TEXT NOT NULL,
              timestamp INTEGER DEFAULT 0,
              PRIMARY KEY(addr))""".format(tbl_name))
        self._conn.commit()

    def drop_table(self, tbl_name):
        self._conn.execute("DROP TABLE IF EXISTS {}".format(tbl_name))
        self._conn.commit()

    def find_proxy(self, tbl_name, addr):
        res = None
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT * FROM {} WHERE addr='{}'".format(tbl_name, addr))
            line = cursor.fetchone()
            if line:
                res = ProxyInfo(*line)
        except Exception:
            raise
        finally:
            cursor.close()
        return res

    def update_timestamp(self, tbl_name, proxy):
        self._conn.execute(
            "REPLACE INTO {} (addr, timestamp) VALUES ('{}', {})".format(tbl_name, proxy.addr, proxy.timestamp))
        self._update_count += 1
        if self._update_count >= self.commit_count:
            self._conn.commit()
            self._update_count = 0


class ProxyInfo:
    IN_QUEUE = 1
    IN_BACKUP = 2

    def __init__(self, addr, timestamp):
        self.addr = addr
        self.timestamp = timestamp
        self.good = 0
        self.bad = 0
        self.fail = 1
        self.status = None
        self.line_index = None
        self.queue_index = None

    @property
    def rate(self):
        return self.good / (self.good + self.bad + 1.0)


class FreehpDb:
    commit_count = 1000
    checker_tbl = "freehp_checker"

    def __init__(self, db_file):
        db_file = abspath(db_file)
        log.debug("Load checker database '{0}'".format(db_file))
        db_dir = dirname(db_file)
        if not exists(db_dir):
            makedirs(db_dir, mode=0o775)
        self._conn = sqlite3.connect(db_file, check_same_thread=False)
        self.create_checker_table()

    def create_checker_table(self):
        self._conn.execute("""CREATE TABLE IF NOT EXISTS {} (
              name TEXT NOT NULL,
              config TEXT NOT NULL,
              PRIMARY KEY(name))""".format(self.checker_tbl))
        self._conn.commit()

    def find_checker(self, name):
        res = None
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT * FROM {} WHERE name='{}'".format(self.checker_tbl, name))
            line = cursor.fetchone()
            if line:
                res = CheckerInfo(*line)
        except Exception:
            raise
        finally:
            cursor.close()
        return res

    def find_checkers(self):
        res = []
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT * FROM {}".format(self.checker_tbl))
            for line in cursor.fetchall():
                res.append(CheckerInfo(*line))
        except Exception:
            raise
        finally:
            cursor.close()
        return res

    def update_checker(self, name, config):
        if not isinstance(config, str):
            config = json.dumps(config)
        self._conn.execute("REPLACE INTO {} (name, config) VALUES ('{}', '{}')".format(self.checker_tbl, name, config))
        self._conn.commit()

    def delete_checker(self, name):
        self._conn.execute("DELETE FROM {} WHERE name='{}'".format(self.checker_tbl, name))
        self._conn.commit()


class CheckerInfo:
    def __init__(self, name, config):
        self.name = name
        self.config = config
        if isinstance(self.config, str):
            self.config = json.loads(config)
