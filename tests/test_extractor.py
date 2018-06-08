# coding=utf-8

from freehp.extractor import extract_proxies


def test_extract_from_table():
    html = """<tr>
        <td height="35"><span class="STYLE1">111.144.121.156</span></td>
        <td width="80"><span class="STYLE1">18186</span></td>
      </tr>
      <tr>
        <td height="35"><span class="STYLE1">111.104.121.156</span></td>
        <td width="80"><span class="STYLE1">8090</span></td>
      </tr>
    """
    assert extract_proxies(html) == ['111.144.121.156:18186', '111.104.121.156:8090']


def test_extract_from_list():
    html = '<div style="padding-left:20px;">201.44.187.69:20183<br>103.106.119.31:8080<br></div>'
    assert extract_proxies(html) == ['201.44.187.69:20183', '103.106.119.31:8080']


def test_extract_form_text():
    html = '193.242.178.90:8080,194.182.81.120:80'
    assert extract_proxies(html) == ['193.242.178.90:8080', '194.182.81.120:80']
