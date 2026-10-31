import urllib.request
import re

url = 'https://game.anichopar.uz'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10) as r:
    html = r.read().decode()

m = re.search(r'src="(/assets/index-[^"]+\.js)"', html)
if m:
    js_url = f'https://game.anichopar.uz{m.group(1)}'
    print('JS bundle:', js_url)
    req2 = urllib.request.Request(js_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req2, timeout=10) as r2:
        js = r2.read().decode()
        if 'api.anichopar.uz/api' in js:
            print('SUCCESS: api.anichopar.uz/api is present in JS bundle!')
        else:
            print('WARNING: api.anichopar.uz/api not found in JS bundle')
