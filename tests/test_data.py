# coding=utf-8

from freehp.data import PriorityQueue


class TestPriorityQueue:
    def test_basic_future(self):
        order = [('+', 5, 10, 5),
                 ('+', 6, 7, 5),
                 ('-', 5, 6),
                 ('-', 6, None),
                 ('+', 5, 6, 5),
                 ('+', 8, 10, 8),
                 ('+', 3, 9, 8),
                 ('+', 6, 7, 8),
                 ('-', 8, 3),
                 ('+', 2, 8, 3),
                 ('+', 1, 5, 3),
                 ('-', 2, 3),
                 ('-', 3, 6),
                 ('-', 6, 5)]

        q = PriorityQueue(5)
        for o in order:
            if o[0] == '+':
                q.push(o[1], o[2])
                assert q.top() == o[3]
            elif o[0] == '-':
                del q[o[1]]
                assert q.top() == o[2]

    def test_is_full(self):
        q = PriorityQueue(3)
        assert not q.is_full()
        q.push(1, 10)
        assert not q.is_full()
        q.push(2, 20)
        assert not q.is_full()
        q.push(3, 30)
        assert q.top() == 3
        assert q.is_full()
        q.push(4, 40)
        assert q.top() == 3
        assert q.is_full()

    def test_update_priority(self):
        q = PriorityQueue(5)
        q.push(1, 10)
        q.push(2, 20)
        assert len(q) == 2
        assert q.top() == 2
        q.push(1, 30)
        assert len(q) == 2
        assert q.top() == 1

    def test_contains(self):
        q = PriorityQueue(3)
        q.push(1, 10)
        q.push(2, 20)
        assert 1 in q and 2 in q
        assert 0 not in q and 3 not in q

    def test_del_no_such_item(self):
        q = PriorityQueue(3)
        del q[0]
