# coding=utf-8

proxy_pages = {
    '89ip': 'http://www.89ip.cn/tqdl.html?num=1000',
    '66ip': 'http://www.66ip.cn/mo.php?tqsl=1000',
    'kuaidaili': ['https://www.kuaidaili.com/free/inha/{}/'.format(i) for i in range(5, 0, -1)]
                 + ['https://www.kuaidaili.com/free/intr/{}/'.format(i) for i in range(5, 0, -1)],
    'data5u': ['http://www.data5u.com/free/gngn/index.shtml',
               'http://www.data5u.com/free/gnpt/index.shtml',
               'http://www.data5u.com/free/gwgn/index.shtml',
               'http://www.data5u.com/free/gwpt/index.shtml'],
    'crossin': ['http://lab.crossincode.com/proxy/', 'http://lab.crossincode.com/proxy/get/?num=20'],
    'ihuan': ['https://ip.ihuan.me/?page={}'.format(i) for i in range(50, 0, -1)]
}
