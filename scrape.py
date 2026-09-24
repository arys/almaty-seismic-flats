"""Scrape Almaty 3-room sale listings from krisha.kz: coordinates (map API) + house type/year (search cards)."""
import json, re, sys, time, html, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = 'https://krisha.kz'
FILTER = 'das[live.rooms]=3'
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36',
      'X-Requested-With': 'XMLHttpRequest'}
OUT = sys.argv[1] if len(sys.argv) > 1 else 'listings.json'


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url.replace('[', '%5B').replace(']', '%5D'), headers=UA)
            return urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
        except Exception as e:
            if i == tries - 1:
                print('FAIL', url, e, file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))


def last_page(pager_html):
    return max(map(int, re.findall(r'data-page="(\d+)"', pager_html or '') or [1]))


def map_page(p):
    s = get(f'{BASE}/a/ajax-map-list/map/prodazha/kvartiry/almaty/?{FILTER}&bounds=43.45,76.7,43.0,77.2&page={p}')
    if not s:
        return {}
    d = json.loads(s)
    ads = d['adverts'].values() if isinstance(d['adverts'], dict) else d['adverts']
    return {a['id']: {'id': a['id'], 'price': a.get('price'), 'square': a.get('square'), 'title': a.get('title'),
                      'address': a.get('addressTitle'), 'complexId': a.get('complexId'), 'owner': a.get('userType'),
                      'lat': (a.get('map') or {}).get('lat'), 'lon': (a.get('map') or {}).get('lon'),
                      'photo': (a.get('photos') or [{}])[0].get('src', '').replace('-full.jpg', '-400x300.jpg')}
            for a in ads}


def text(s):
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()


def search_page(p):
    s = get(f'{BASE}/prodazha/kvartiry/almaty/?{FILTER}&page={p}')
    if not s:
        return {}
    out = {}
    for card in s.split('data-id="')[1:]:
        m = re.match(r'(\d+)"', card)
        if not m or 'a-card__descr' not in card[:6000]:
            continue
        sub = re.search(r'a-card__subtitle[^>]*>(.*?)</div>', card, re.S)
        prev = re.search(r'a-card__text-preview[^>]*>(.*?)</div>', card, re.S)
        out[int(m.group(1))] = {'district': text(sub.group(1)) if sub else '', 'preview': text(prev.group(1)) if prev else ''}
    return out


def run(fn, pages, label):
    res = {}
    with ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(fn, pages)):
            res.update(r)
            if i % 50 == 0:
                print(label, i, '/', len(pages), len(res), flush=True)
    return res


first = json.loads(get(f'{BASE}/a/ajax-map-list/map/prodazha/kvartiry/almaty/?{FILTER}&bounds=43.45,76.7,43.0,77.2&page=1'))
n_map = last_page(first['pager'])
s1 = get(f'{BASE}/prodazha/kvartiry/almaty/?{FILTER}')
n_search = last_page(re.search(r'class="paginator.*?</nav>', s1, re.S).group(0))
print('pages: map', n_map, 'search', n_search, flush=True)

coords = run(map_page, range(1, n_map + 1), 'map')
details = run(search_page, range(1, n_search + 1), 'search')

rows = []
for i, a in coords.items():
    d = details.get(i, {})
    pv = d.get('preview', '')
    a['district'] = d.get('district', '')
    a['houseType'] = (re.search(r'(монолитный|кирпичный|панельный|каркасно-камышитовый|иное)', pv) or [None])[0]
    y = re.search(r'(\d{4}) г\.п\.', pv)
    a['year'] = int(y.group(1)) if y else None
    f = re.search(r'(\d+)/(\d+) этаж', a.get('title') or '')
    a['floor'], a['floors'] = (int(f.group(1)), int(f.group(2))) if f else (None, None)
    a['preview'] = pv[:200]
    rows.append(a)
json.dump(rows, open(OUT, 'w'), ensure_ascii=False)
print('saved', len(rows), 'with details', sum(1 for r in rows if r['houseType']), flush=True)
