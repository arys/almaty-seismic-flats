"""Tag listings in raw/*.json with seismic zone + distance to nearest fault; write data/*.js and a clean zones overlay."""
import glob, json, math, os
from collections import Counter, defaultdict
from datetime import date
import numpy as np, cv2

B = 8                                   # block size in full-res px (counts2.npy is per block)
counts = np.load('counts2.npy') / (B * B)
fault = np.load('fault.npy')
fit = json.load(open('fit.json')); s, ang, asp, tx, ty = fit['p']; cx, cy = fit['c']
R = 6378137
hb, wb = fault.shape

# zone label per block: 0 = 9, 1 = 9/10, 2 = 10, -1 unknown; fill gaps (roads, fault bands) from nearest zone
z = cv2.blur(counts[:3].transpose(1, 2, 0), (3, 3))
lab = np.where(z.max(-1) > 0.06, z.argmax(-1), -1).astype(np.int8)
lab[:400, :450] = -1                                            # legend
unk = (lab < 0).astype(np.uint8)
dist, idx = cv2.distanceTransformWithLabels(unk, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
lut = np.zeros(idx.max() + 1, np.int8); lut[idx[unk == 0]] = lab[unk == 0]
filled = np.where((unk == 1) & (dist <= 14), lut[idx], lab)

fdist = cv2.distanceTransform((1 - fault).astype(np.uint8), cv2.DIST_L2, 5)   # blocks to nearest fault

def ll2block(lat, lon):
    mx = R * math.radians(lon); my = R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    xs = s * (mx - cx) + tx; ys = -s * asp * (my - cy) + ty          # small (1/10) image px
    return int(xs * 10 / B), int(ys * 10 / B)

def block2ll(bx, by):
    xs = bx * B / 10 - tx; ys = by * B / 10 - ty
    mx = xs / s + cx; my = -ys / (s * asp) + cy
    return math.degrees(2 * math.atan(math.exp(my / R)) - math.pi / 2), math.degrees(mx / R)

m_per_block = B / 10 / s * math.cos(math.radians(43.25))            # true ground metres

DEALS = {'prodazha': 'sale', 'arenda': 'rent'}
PRICE_OK = {'sale': lambda p: p >= 5_000_000,               # below = rent posted as sale, or typo
            'rent': lambda p: 60_000 <= p <= 5_000_000}     # monthly; outside = daily rent or sale price
sets = {}
for path in sorted(glob.glob('raw/*.json')):
    deal, rooms = os.path.basename(path)[:-5].split('-')
    sets[f'{DEALS[deal]}-{rooms}'] = json.load(open(path))

# rent ads rarely state house type/year: borrow them from other ads in the same complex, else the same building
def mode(vals):
    vals = [v for v in vals if v]
    return Counter(vals).most_common(1)[0][0] if vals else None
by_complex, by_point = defaultdict(list), defaultdict(list)
for rows in sets.values():
    for r in rows:
        if r.get('lat'):
            if r.get('complexId'):
                by_complex[r['complexId']].append(r)
            by_point[(round(r['lat'], 4), round(r['lon'], 4))].append(r)

os.makedirs('data', exist_ok=True)
meta = {'updated': date.today().isoformat(), 'counts': {}}
for key, rows in sets.items():
    out = []
    for r in rows:
        if not r.get('lat') or not r.get('price') or not PRICE_OK[key.split('-')[0]](r['price']):
            continue
        ht, y, inferred = r.get('houseType'), r.get('year'), False
        if not ht or not y:
            peers = by_complex.get(r.get('complexId')) or by_point.get((round(r['lat'], 4), round(r['lon'], 4)), [])
            ht2, y2 = mode(p.get('houseType') for p in peers), mode(p.get('year') for p in peers)
            inferred = (not ht and bool(ht2)) or (not y and bool(y2))
            ht, y = ht or ht2, y or y2
        bx, by = ll2block(r['lat'], r['lon'])
        inside = 0 <= bx < wb and 0 <= by < hb
        o = {'id': r['id'], 'la': round(r['lat'], 6), 'lo': round(r['lon'], 6), 'p': r['price'], 'sq': r['square'],
             'fl': r['floor'], 'fls': r['floors'], 'a': r['address'], 'd': r['district'], 'ht': ht, 'y': y,
             'z': int(filled[by, bx]) if inside else -1,
             'fd': round(float(fdist[by, bx]) * m_per_block) if inside else None, 'ph': r['photo'], 'rm': r['rooms']}
        if inferred:
            o['inf'] = 1
        out.append(o)
    # one listing per line, sorted by id: keeps daily git diffs small
    with open(f'data/{key}.js', 'w') as f:
        f.write(f'(window.DATA = window.DATA || {{}})["{key}"] = [\n')
        f.write(',\n'.join(json.dumps(o, ensure_ascii=False, separators=(',', ':')) for o in out))
        f.write('\n];\n')
    meta['counts'][key] = len(out)
    print(key, len(out), 'zones', dict(Counter(o['z'] for o in out)), 'inferred', sum('inf' in o for o in out),
          'no type', sum(not o['ht'] for o in out))
with open('data/meta.js', 'w') as f:
    f.write('window.META = ' + json.dumps(meta) + ';\n')

# clean overlay: 9 mint, 9/10 yellow, 10 red, faults dark hatch
rgba = np.zeros((hb, wb, 4), np.uint8)
colors = {0: (60, 200, 140), 1: (240, 210, 0), 2: (230, 40, 40)}
for k, c in colors.items():
    rgba[filled == k] = (*c, 150)
rgba[fault == 1] = (90, 50, 0, 200)
cv2.imwrite('zones-clean.png', cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
