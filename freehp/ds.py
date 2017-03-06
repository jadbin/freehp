# coding=utf-8

from collections import deque


class PriorityQueue:
    def __init__(self, size):
        self._size = size
        self._base = 1
        while self._base < size:
            self._base <<= 1
        self._h = [None] * (self._base * 2)
        self._v, self._p = [None] * self._base, [None] * self._base
        self._init_heap()
        self._q = self._storage(size)

    def __len__(self):
        return self._size - len(self._q)

    def __delitem__(self, index):
        if len(self._q) < self._size:
            i = self._h[1] if index is None else index
            self._p[i] = None
            self._update(i)
            self._q.append(i)

    def is_full(self):
        return len(self._q) == 0

    def push(self, item, priority):
        if len(self._q) > 0:
            i = self._q.popleft()
            self._v[i], self._p[i] = item, priority
            self._update(i)
            return i

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
    def _storage(size):
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
