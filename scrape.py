"""Scrape Almaty apartment listings from krisha.kz: coordinates (map API) + house type/year (search cards).

Writes raw/<deal>-<rooms>.json for every (deal, rooms) combination in SETS.
"""
import json, os, re, sys, time, html, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

BASE = 'https://krisha.kz'
SETS = [('prodazha', 2), ('prodazha', 3), ('arenda', 2), ('arenda', 3)]
BOUNDS = '43.45,76.7,43.0,77.2'
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36',
      'X-Requested-With': 'XMLHttpRequest'}
OUT = 'raw'


def get(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url.replace('[', '%5B').replace(']', '%5D'), headers=UA)
            return urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
        except Exception as e:
            if i == tries - 1:
                print('FAIL', url, e, file=sys.stderr)
                return None
            # 468 = krisha rate limit; back off harder
            time.sleep((20 if isinstance(e, urllib.error.HTTPError) and e.code == 468 else 2) * (i + 1))


def last_page(pager_html):
    return max(map(int, re.findall(r'data-page="(\d+)"', pager_html or '') or [1]))


def text(s):
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()


def map_url(deal, rooms, p):
    return f'{BASE}/a/ajax-map-list/map/{deal}/kvartiry/almaty/?das[live.rooms]={rooms}&bounds={BOUNDS}&page={p}'


def search_url(deal, rooms, p):
    return f'{BASE}/{deal}/kvartiry/almaty/?das[live.rooms]={rooms}&page={p}'


def map_page(deal, rooms, p):
    s = get(map_url(deal, rooms, p))
    if not s:
        return {}
    d = json.loads(s)
    ads = d['adverts'].values() if isinstance(d['adverts'], dict) else d['adverts']
    return {a['id']: {'id': a['id'], 'price': a.get('price'), 'square': a.get('square'), 'title': a.get('title'),
                      'address': a.get('addressTitle'), 'complexId': a.get('complexId'), 'owner': a.get('userType'),
                      'lat': (a.get('map') or {}).get('lat'), 'lon': (a.get('map') or {}).get('lon'),
                      'photo': (a.get('photos') or [{}])[0].get('src', '').replace('-full.jpg', '-400x300.jpg')}
            for a in ads}


def search_page(deal, rooms, p):
    s = get(search_url(deal, rooms, p))
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


def run(fn, n, label):
    res = {}
    with ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(fn, range(1, n + 1))):
            res.update(r)
            if i % 100 == 0:
                print(label, i, '/', n, len(res), flush=True)
    return res


def scrape(deal, rooms):
    label = f'{deal}-{rooms}'
    first = get(map_url(deal, rooms, 1))
    s1 = get(search_url(deal, rooms, 1))
    if not first or not s1:
        raise SystemExit(f'{label}: krisha unreachable')
    n_map = last_page(json.loads(first)['pager'])
    pager = re.search(r'class="paginator.*?</nav>', s1, re.S)
    n_search = last_page(pager.group(0) if pager else '')
    print(label, 'pages: map', n_map, 'search', n_search, flush=True)

    coords = run(lambda p: map_page(deal, rooms, p), n_map, label + ' map')
    details = run(lambda p: search_page(deal, rooms, p), n_search, label + ' search')

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
        a['rooms'] = rooms
        rows.append(a)
    rows.sort(key=lambda r: r['id'])
    # a run that lost many pages (rate limit) must not replace good data
    if len(rows) < 0.8 * 20 * (n_map - 1):
        raise SystemExit(f'{label}: only {len(rows)} rows for {n_map} pages, aborting')
    json.dump(rows, open(f'{OUT}/{label}.json', 'w'), ensure_ascii=False)
    print(label, 'saved', len(rows), 'with details', sum(1 for r in rows if r['houseType']), flush=True)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for deal, rooms in SETS:
        scrape(deal, rooms)
