"""Tag each listing with seismic zone + distance to nearest fault; write data.js and a clean zones overlay."""
import json, math, numpy as np, cv2

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

rows = json.load(open('listings.json'))
out = []
for r in rows:
    if not r.get('lat') or not r.get('price') or r['price'] < 5_000_000:   # <5M ₸ = rent posted as sale, or typo
        continue
    bx, by = ll2block(r['lat'], r['lon'])
    inside = 0 <= bx < wb and 0 <= by < hb
    zone = int(filled[by, bx]) if inside else -1
    fd = round(float(fdist[by, bx]) * m_per_block) if inside else None
    out.append({'id': r['id'], 'la': round(r['lat'], 6), 'lo': round(r['lon'], 6), 'p': r['price'], 'sq': r['square'],
                'fl': r['floor'], 'fls': r['floors'], 'a': r['address'], 'd': r['district'], 'ht': r['houseType'],
                'y': r['year'], 'z': zone, 'fd': fd, 'ph': r['photo'], 'o': r['owner']})
with open('data.js', 'w') as f:
    f.write('window.LISTINGS=' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n')

# clean overlay: 9 mint, 9/10 yellow, 10 red, faults dark hatch
rgba = np.zeros((hb, wb, 4), np.uint8)
colors = {0: (60, 200, 140), 1: (240, 210, 0), 2: (230, 40, 40)}
for k, c in colors.items():
    rgba[filled == k] = (*c, 150)
rgba[fault == 1] = (90, 50, 0, 200)
cv2.imwrite('zones-clean.png', cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
n, w = block2ll(0, 0); S, e = block2ll(wb, hb)
print('bounds', [[S, w], [n, e]], 'listings', len(out), 'm/block', m_per_block)
from collections import Counter
print(Counter(o['z'] for o in out), sum(1 for o in out if o['fd'] is not None and o['fd'] < 300))
