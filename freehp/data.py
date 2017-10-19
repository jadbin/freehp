# coding=utf-8

from os import makedirs
from os.path import dirname, abspath, exists
import logging
import sqlite3
from collections import deque

log = logging.getLogger(__name__)


class ProxyDb:
    tbl_name = 'agent_proxy'
    commit_count = 1000

    def __init__(self, db_file):
        db_file = abspath(db_file)
        log.debug("Load proxy database '{0}'".format(db_file))
        db_dir = dirname(db_file)
        if not exists(db_dir):
            makedirs(db_dir, mode=0o775)
        self._conn = sqlite3.connect(db_file, check_same_thread=False)
        self._update_count = 0

    def create_table(self):
        self.drop_table()
        self._conn.execute("""CREATE TABLE {} (
              addr TEXT NOT NULL,
              timestamp INTEGER DEFAULT 0,
              PRIMARY KEY(addr))""".format(self.tbl_name))
        self._conn.commit()

    def drop_table(self):
        self._conn.execute("DROP TABLE IF EXISTS {}".format(self.tbl_name))
        self._conn.commit()

    def find_proxy(self, addr):
        res = None
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT * FROM {} WHERE addr='{}'".format(self.tbl_name, addr))
            line = cursor.fetchone()
            if line:
                res = ProxyInfo(*line)
        except Exception:
            raise
        finally:
            cursor.close()
        return res

    def update_timestamp(self, proxy):
        self._conn.execute(
            "REPLACE INTO {} (addr, timestamp) VALUES ('{}', {})".format(self.tbl_name, proxy.addr, proxy.timestamp))
        self._update_count += 1
        if self._update_count >= self.commit_count:
            self._conn.commit()
            self._update_count = 0


class ProxyInfo:
    def __init__(self, addr, timestamp, *, good=0, bad=0, fail=1):
        self.addr = addr
        self.timestamp = timestamp
        self.good = good
        self.bad = bad
        self.fail = fail

    @property
    def rate(self):
        return self.good / (self.good + self.bad + 1.0)


class PriorityQueue:
    def __init__(self, size):
        self._size = size
        self._base = 1
        while self._base < size:
            self._base <<= 1
        self._h = [None] * (self._base * 2)
        self._v, self._p = [None] * self._base, [None] * self._base
        self._init_heap()
        self._q = self._memory_queue(size)
        self._index = {}

    def __len__(self):
        return self._size - len(self._q)

    def __contains__(self, item):
        return id(item) in self._index

    def __delitem__(self, item):
        ii = id(item)
        if ii not in self._index:
            return
        i = self._index[ii]
        self._p[i] = None
        self._update(i)
        self._q.append(i)
        del self._index[ii]

    def is_full(self):
        return len(self._q) == 0

    def push(self, item, priority):
        ii = id(item)
        if ii in self._index:
            i = self._index[ii]
            self._p[i] = priority
            self._update(i)
        else:
            if len(self._q) > 0:
                i = self._q.popleft()
                self._index[ii] = i
                self._v[i], self._p[i] = item, priority
                self._update(i)

    def top(self):
        if len(self._q) < self._size:
            i = self._h[1]
            return self._v[i]

    def _init_heap(self):
        i = 0
        while i < self._base:
            self._h[self._base + i] = i
            i += 1
        i = self._base - 1
        while i > 0:
            self._h[i] = self._prefer(self._h[i << 1], self._h[i << 1 | 1])
            i -= 1

    @staticmethod
    def _memory_queue(size):
        q = deque(maxlen=size)
        i = 0
        while i < size:
            q.append(i)
            i += 1
        return q

    def _prefer(self, x, y):
        vx, vy = self._p[x], self._p[y]
        if vy is None:
            return x
        if vx is None:
            return y
        return x if vx >= vy else y

    def _update(self, i):
        i += self._base
        i >>= 1
        while i >= 1:
            self._h[i] = self._prefer(self._h[i << 1], self._h[i << 1 | 1])
            i >>= 1
