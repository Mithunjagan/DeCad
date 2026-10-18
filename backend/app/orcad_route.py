"""Orthogonal wire routing for generated OrCAD Capture pages.

Works on the placed page read back from the saved design (orcad_capture.drawing): every pin's hotspot,
direction and the part bodies. Pins of one net are joined by right-angle wires on Capture's 0.1 inch
grid; a net that cannot be wired cleanly gets a short stub with its net label instead (as Capture users
do for buses and off-sheet signals). Wires of different nets never touch: they may only cross straight
through each other (a crossing is not a connection in Capture), never bend, end or join on another
net's wire, and never pass over a part body, a pin line or another pin's end. Each pin keeps a short
private stretch in front of it, so a fallback label always fits. The saved design is still checked
pin by pin afterwards, so a routing mistake cannot pass unnoticed.
"""
import heapq

G = 10            # Capture grid (1/10 inch, in 1/100 inch units)
STUB = 3          # cells of private stretch / label stub in front of each pin
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
BEND, CROSS = 6, 4
MAX_PINS = 12     # larger nets (buses, clocks to many parts) keep labels
MAX_EXPAND = 60000


def _sign(v):
    return (v > 0) - (v < 0)


def _body_box(part, place):
    """Bounding box of the drawn symbol in page coordinates (vectors and pin start points)."""
    t = place(part)
    xs, ys = [], []
    for v in part['vectors']:
        n = v[1:]
        pts = [(n[i], n[i + 1]) for i in range(1 if v[0] == 'POLY' else 0, len(n) - 1, 2)][:4 if v[0] != 'POLY' else None]
        for x, y in pts:
            x, y = t(x, y); xs.append(x); ys.append(y)
    for p in part['pins']:
        xs.append(p['sx']); ys.append(p['sy'])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


class Router:
    def __init__(self, page, pin_net, place):
        self.W, self.H = page['width'] // G, page['height'] // G
        self.blocked = set()        # bodies and pin lines: nothing may enter
        self.owner = {}             # hotspot / private stretch cell -> net (None = unconnected pin)
        self.occ = {}               # wire cell -> (net, 'H' | 'V' | 'N' | 'C')
        self.pins = {}              # net -> [(hotspot cell, out dir, on grid, (hx, hy))]
        self.labelled = {}          # net -> pins that get a stub + label
        for part in page['parts']:
            box = _body_box(part, place)
            if box:
                x0, y0, x1, y1 = (int(box[0] // G), int(box[1] // G), -(-int(box[2]) // G), -(-int(box[3]) // G))
                for x in range(x0, x1 + 1):
                    for y in range(y0, y1 + 1):
                        self.blocked.add((x, y))
        for part in page['parts']:
            for p in part['pins']:
                net = pin_net.get((part['base'], str(p['number'])))
                hx, hy, sx, sy = p['hx'], p['hy'], p['sx'], p['sy']
                d = (_sign(hx - sx), _sign(hy - sy))
                if d[0] and d[1]:
                    d = (d[0], 0) if abs(hx - sx) >= abs(hy - sy) else (0, d[1])
                if d == (0, 0):
                    d = (-1, 0)
                grid = hx % G == 0 and hy % G == 0
                h = (hx // G, hy // G)
                # the pin line belongs to the symbol
                c = (sx // G, sy // G)
                while grid and c != h and abs(c[0] - h[0]) + abs(c[1] - h[1]) < 200:
                    self.blocked.add(c)
                    c = (c[0] + _sign(h[0] - c[0]), c[1] + _sign(h[1] - c[1]))
                self.blocked.discard(h)
                self.owner[h] = net
                for k in range(1, STUB + 1):
                    cell = (h[0] + d[0] * k, h[1] + d[1] * k)
                    self.blocked.discard(cell)
                    self.owner.setdefault(cell, net)
                if net is not None:
                    self.pins.setdefault(net, []).append((h, d, grid, (hx, hy)))
        self.edges = {}             # net -> set of frozenset({a, b}) unit edges

    # ------------------------------------------------------------------ search
    def _enter(self, cell, net, axis, targets, start):
        """(allowed, extra cost, must go straight, is goal) for entering a cell moving along an axis."""
        if cell in targets:
            return True, 0, False, True
        x, y = cell
        if x < 1 or y < 1 or x >= self.W - 1 or y >= self.H - 1 or cell in self.blocked:
            return False, 0, False, False
        if cell in self.owner:
            o = self.owner[cell]
            if o != net or cell in self.hotspots or (cell not in self.own_lane and cell not in start):
                return False, 0, False, False
        o = self.occ.get(cell)
        if o is None:
            return True, 0, False, False
        if o[0] == net:
            return False, 0, False, False          # own wire that is not a target (a crossing point)
        if (o[1] == 'H' and axis == 'V') or (o[1] == 'V' and axis == 'H'):
            return True, CROSS, True, False
        return False, 0, False, False

    def _search(self, net, src, d0, targets, goal_hint):
        sx, sy = src
        first = (sx + d0[0], sy + d0[1])
        start = {src}
        ok, extra, straight, goal = self._enter(first, net, 'H' if d0[0] else 'V', targets, start)
        if not ok:
            return None
        if goal:
            return [src, first]
        hint = lambda c: min(abs(c[0] - t[0]) + abs(c[1] - t[1]) for t in goal_hint)
        di = DIRS.index(d0)
        startstate = (first, di)
        g = {startstate: 1 + extra}
        parent = {startstate: None}
        straight_at = {first: straight}
        heap = [(1 + extra + hint(first), 1 + extra, first, di)]
        n = 0
        while heap:
            f, cost, cell, di = heapq.heappop(heap)
            if cost > g.get((cell, di), 1e18):
                continue
            n += 1
            if n > MAX_EXPAND:
                return None
            for ndi, (dx, dy) in enumerate(DIRS):
                if ndi != di and (straight_at.get(cell) or (dx, dy) == (-DIRS[di][0], -DIRS[di][1])):
                    continue
                nxt = (cell[0] + dx, cell[1] + dy)
                ok, extra, straight, goal = self._enter(nxt, net, 'H' if dx else 'V', targets, start)
                if not ok:
                    continue
                if goal and straight_at.get(cell) and ndi != di:
                    continue
                nc = cost + 1 + extra + (BEND if ndi != di else 0)
                key = (nxt, ndi)
                if nc >= g.get(key, 1e18):
                    continue
                g[key] = nc
                parent[key] = (cell, di)
                if goal:
                    path, k = [nxt], (cell, di)
                    while k:
                        path.append(k[0]); k = parent[k]
                    path.append(src)
                    return path[::-1]
                straight_at[nxt] = straight
                heapq.heappush(heap, (nc + hint(nxt), nc, nxt, ndi))
        return None

    # ------------------------------------------------------------------ commit
    def _commit(self, net, path):
        edges = self.edges.setdefault(net, set())
        for a, b in zip(path, path[1:]):
            edges.add(frozenset((a, b)))
        for i, c in enumerate(path):
            prev, nxt = (path[i - 1] if i else None), (path[i + 1] if i + 1 < len(path) else None)
            other = self.occ.get(c)
            if other and other[0] != net:
                self.occ[c] = (None, 'C')          # crossing: closed to everyone from now on
                continue
            if prev and nxt and (prev[0] == nxt[0] or prev[1] == nxt[1]) and not other:
                self.occ[c] = (net, 'V' if prev[0] == nxt[0] else 'H')
            else:
                self.occ[c] = (net, 'N')

    def route(self, max_pins=MAX_PINS):
        nets = sorted(self.pins, key=lambda n: (len(self.pins[n]), self._span(n)))
        self.hotspots = {h for pins in self.pins.values() for h, _, _, _ in pins} | {h for h, n in self.owner.items() if n is None}
        wired = []
        for net in nets:
            pins = self.pins[net]
            if len(pins) < 2 or len(pins) > max_pins or not all(p[2] for p in pins):
                self.labelled[net] = pins
                continue
            self.own_lane = {(h[0] + d[0] * k, h[1] + d[1] * k) for h, d, _, _ in pins for k in range(1, STUB + 1)}
            done = [pins[0]]
            todo = pins[1:]
            failed = []
            while todo:
                tree = {p[0] for p in done} | {c for c, o in self.occ.items() if o[0] == net and o[1] in ('H', 'V', 'N')}
                todo.sort(key=lambda p: min(abs(p[0][0] - q[0][0]) + abs(p[0][1] - q[0][1]) for q in done))
                p = todo.pop(0)
                path = self._search(net, p[0], p[1], tree, [q[0] for q in done])
                if path is None:
                    failed.append(p); continue
                self._commit(net, path)
                done.append(p)
            if len(done) > 1:
                self.occ[pins[0][0]] = (net, 'N')
                wired.append(net)
            if failed or len(done) == 1:
                self.labelled[net] = failed if len(done) > 1 else pins
        return wired

    def _span(self, net):
        xs = [p[0][0] for p in self.pins[net]]; ys = [p[0][1] for p in self.pins[net]]
        return max(xs) - min(xs) + max(ys) - min(ys)

    # ------------------------------------------------------------------ output
    def segments(self, net):
        """Unit edges of a net merged into straight wires that end at every bend, junction and pin."""
        adj = {}
        for e in self.edges.get(net, ()):
            a, b = tuple(e)
            adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
        def through(c):
            n = adj.get(c, ())
            if len(n) != 2 or c in self.hotspots:
                return False
            a, b = tuple(n)
            return a[0] == b[0] == c[0] or a[1] == b[1] == c[1]
        segs, seen = [], set()
        for c in adj:
            if through(c):
                continue
            for nb in adj[c]:
                if frozenset((c, nb)) in seen:
                    continue
                prev, cur = c, nb
                seen.add(frozenset((prev, cur)))
                while through(cur):
                    nxt = next(x for x in adj[cur] if x != prev)
                    prev, cur = cur, nxt
                    seen.add(frozenset((prev, cur)))
                segs.append((c, cur))
        return segs


def route(page, pin_net, place, max_pins=MAX_PINS):
    """Wires for one page: [(x1, y1, x2, y2, alias, ax, ay)] and a summary."""
    r = Router(page, pin_net, place)
    wired = r.route(max_pins)
    out = []
    for net in wired:
        segs = r.segments(net)
        if not segs:
            continue
        longest = max(segs, key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
        for a, b in segs:
            alias = ''
            ax = ay = 0
            if (a, b) == longest:
                alias = net
                ax, ay = (a[0] + b[0]) // 2 * G, (a[1] + b[1]) // 2 * G
            out.append((a[0] * G, a[1] * G, b[0] * G, b[1] * G, alias, ax, ay))
    stubs = 0
    for net, pins in r.labelled.items():
        for h, d, grid, (hx, hy) in pins:
            ex, ey = hx + d[0] * STUB * G, hy + d[1] * STUB * G
            out.append((hx, hy, ex, ey, net, ex, ey))
            stubs += 1
    crossings = sum(1 for o in r.occ.values() if o[1] == 'C')
    return out, {'wired_nets': len(wired), 'labelled_pins': stubs, 'crossings': crossings,
                 'labelled_nets': len([n for n in r.labelled if n not in wired])}
