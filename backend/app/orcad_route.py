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
    def __init__(self, page, pin_net, place, *, stub_cells=STUB, grid=G):
        self.stub = stub_cells
        self.last_failure = None
        self.grid = grid
        self.W, self.H = page['width'] // grid, page['height'] // grid
        self.blocked = set()        # bodies and pin lines: nothing may enter
        self.owner = {}             # hotspot / private stretch cell -> net (None = unconnected pin)
        self.occ = {}               # wire cell -> (net, 'H' | 'V' | 'N' | 'C')
        self.pins = {}              # net -> [(hotspot cell, out dir, on grid, (hx, hy))]
        self.labelled = {}          # net -> pins that get a stub + label
        self.source_crossings=set()
        for part in page['parts']:
            vectors = part['vectors']
            # A split IC may have separate source bodies. The gap between its
            # sections remains a routing channel rather than one solid obstacle.
            ports = part['base'].startswith(('P','J')) and vectors and all(v[0]=='LINE' for v in vectors)
            boxes = [] if ports else [_body_box({**part,'vectors':[v],'pins':[]},place) for v in vectors] if len(vectors)>1 and all(v[0]=='BOX' for v in vectors) else [_body_box(part, place)]
            for box in filter(None,boxes):
                x0, y0, x1, y1 = (int(box[0] // grid), int(box[1] // grid), -(-int(box[2]) // grid), -(-int(box[3]) // grid))
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
                on_grid = hx % grid == 0 and hy % grid == 0
                h = (hx // grid, hy // grid)
                # the pin line belongs to the symbol
                c = (sx // grid, sy // grid)
                while on_grid and c != h and abs(c[0] - h[0]) + abs(c[1] - h[1]) < 400:
                    self.blocked.add(c)
                    c = (c[0] + _sign(h[0] - c[0]), c[1] + _sign(h[1] - c[1]))
                self.blocked.discard(h)
                self.owner[h] = net
                for k in range(1, self.stub + 1):
                    cell = (h[0] + d[0] * k, h[1] + d[1] * k)
                    self.blocked.discard(cell)
                    self.owner.setdefault(cell, net)
                if net is not None:
                    self.pins.setdefault(net, []).append((h, d, on_grid, (hx, hy)))
        self.edges = {}             # net -> set of frozenset({a, b}) unit edges

    # ------------------------------------------------------------------ search
    def _enter(self, cell, net, axis, targets, start):
        """(allowed, extra cost, must go straight, is goal) for entering a cell moving along an axis."""
        if cell in targets and cell not in self.source_crossings:
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
            return True, 0, cell in self.source_crossings, False
        if o[0] == net:
            return (True, 0, cell in self.source_crossings, False) if o[1] != 'C' else (False, 0, False, False)
        if (o[1] == 'H' and axis == 'V') or (o[1] == 'V' and axis == 'H'):
            return True, CROSS, True, False
        return False, 0, False, False

    def _search(self, net, src, d0, targets, goal_hint, *, weight=2, budget=MAX_EXPAND):
        self.last_failure = None
        sx, sy = src
        first = (sx + d0[0], sy + d0[1])
        start = {src}
        ok, extra, straight, goal = self._enter(first, net, 'H' if d0[0] else 'V', targets, start)
        if not ok:
            self.last_failure = 'pin escape blocked'
            return None
        if goal:
            return [src, first]
        hint = lambda c: min(abs(c[0] - t[0]) + abs(c[1] - t[1]) for t in goal_hint)
        di = DIRS.index(d0)
        startstate = (first, di)
        g = {startstate: 1 + extra}
        parent = {startstate: None}
        straight_at = {first: straight}
        # Prefer deeper paths when estimated costs tie. Preferring shallow paths
        # floods a large empty source sheet before reaching a distant supply rail.
        heap = [(1 + extra + weight*hint(first), -(1 + extra), first, di)]
        n = 0
        while heap:
            f, negative_cost, cell, di = heapq.heappop(heap)
            cost = -negative_cost
            if cost > g.get((cell, di), 1e18):
                continue
            n += 1
            if n > budget:
                if weight == 2:
                    return self._search(net, src, d0, targets, goal_hint, weight=4, budget=4*MAX_EXPAND)
                self.last_failure = 'search budget'
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
                heapq.heappush(heap, (nc + weight*hint(nxt), -nc, nxt, ndi))
        self.last_failure = 'no path'
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
        self.failures = {}
        self.hotspots = {h for pins in self.pins.values() for h, _, _, _ in pins} | {h for h, n in self.owner.items() if n is None}
        wired = []
        for net in nets:
            pins = self.pins[net]
            if len(pins) < 2 or len(pins) > max_pins or not all(p[2] for p in pins):
                self.labelled[net] = pins
                continue
            self.own_lane = {(h[0] + d[0] * k, h[1] + d[1] * k) for h, d, _, _ in pins for k in range(1, self.stub + 1)}
            done = [pins[0]]
            todo = pins[1:]
            failed = []
            while todo:
                tree = self.connected_cells(net, {p[0] for p in done})-self.source_crossings
                todo.sort(key=lambda p: min(abs(p[0][0] - q[0][0]) + abs(p[0][1] - q[0][1]) for q in done))
                p = todo.pop(0)
                if p[0] in tree:
                    done.append(p);continue
                path = self._search(net, p[0], p[1], tree, [q[0] for q in done])
                if path is None:
                    self.failures.setdefault(net, []).append(self.last_failure)
                    failed.append(p); continue
                self._commit(net, path)
                done.append(p)
            if len(done) > 1:
                self.occ[pins[0][0]] = (net, 'N')
                wired.append(net)
            if failed or len(done) == 1:
                self.labelled[net] = failed if len(done) > 1 else pins
        return wired

    def connected_cells(self, net, starts):
        adjacency = {}
        for edge in self.edges.get(net, ()):
            a,b=tuple(edge)
            adjacency.setdefault(a,set()).add(b);adjacency.setdefault(b,set()).add(a)
        found=set(starts);pending=[(None,p) for p in starts];states=set(pending)
        while pending:
            previous,current=pending.pop()
            neighbors=adjacency.get(current,())
            if current in self.source_crossings and previous is not None:
                opposite=(2*current[0]-previous[0],2*current[1]-previous[1])
                neighbors=[opposite] if opposite in neighbors else []
            for point in neighbors:
                state=(current,point)
                if state not in states:
                    states.add(state);found.add(point);pending.append(state)
        return found

    def _span(self, net):
        xs = [p[0][0] for p in self.pins[net]]; ys = [p[0][1] for p in self.pins[net]]
        return max(xs) - min(xs) + max(ys) - min(ys)

    def prune_leaves(self,net):
        """Remove every non-terminal leaf, including chains left by bad seeds."""
        edges=self.edges.get(net,set());adj={}
        for edge in edges:
            a,b=tuple(edge);adj.setdefault(a,set()).add(b);adj.setdefault(b,set()).add(a)
        terminals={p[0] for p in self.pins.get(net,[])}
        pending=[p for p,n in adj.items() if len(n)==1 and p not in terminals]
        removed=0
        while pending:
            point=pending.pop()
            if point in terminals or len(adj[point])!=1:continue
            other=adj[point].pop();adj[other].remove(point)
            edges.discard(frozenset((point,other)));removed+=1
            if len(adj[other])==1 and other not in terminals:pending.append(other)
        return removed

    # ------------------------------------------------------------------ output
    def segments(self, net):
        """Unit edges of a net merged into straight wires that end at every bend, junction and pin."""
        adj = {}
        for e in self.edges.get(net, ()):
            a, b = tuple(e)
            adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
        def through(c):
            n = adj.get(c, ())
            if c in self.source_crossings and len(n)==4:return True
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
                    if cur in self.source_crossings:
                        nxt=(2*cur[0]-prev[0],2*cur[1]-prev[1])
                        if nxt not in adj[cur]:break
                    else:nxt = next(x for x in adj[cur] if x != prev)
                    prev, cur = cur, nxt
                    seen.add(frozenset((prev, cur)))
                segs.append((c, cur))
        return segs


def route(page, pin_net, place, max_pins=MAX_PINS, *, require_wires=False, source_paths=(), source_report=None, named_aliases=None, gap_evidence=None, observed_stub_nets=()):
    """Wires for one page: [(x1, y1, x2, y2, alias, ax, ay)] and a summary."""
    r = Router(page, pin_net, place)
    if require_wires:
        # Raw image fragments never become native wires. Route from actual
        # placed terminals, whose grid coordinates are the sole authority.
        source_paths=();gap_evidence=None
    if source_report is not None and not require_wires:
        r.source_crossings={tuple(int(v//r.grid) for v in c['at']) for c in source_report.get('source_crossings',[])}
    if source_paths:
        from .orcad_source_wires import seed
        seed(r,source_paths,source_report)
    source_edges={net:set(edges) for net,edges in r.edges.items()}
    wired = r.route(max(len(pins) for pins in r.pins.values()) if require_wires and r.pins else max_pins)
    pruned=sum(r.prune_leaves(net) for net in list(r.edges)) if require_wires else 0
    if source_report is not None and gap_evidence is not None:
        from .orcad_wire_gaps import repair
        for net,edges in repair(r,gap_evidence,source_report).items():
            source_edges.setdefault(net,set()).update(edges)
    out = []
    segment_nets=[]
    drawn=list(wired)
    for net,pins in r.pins.items():
        if net in wired or len(pins)!=1:continue
        connected=r.connected_cells(net,{pins[0][0]})
        if len(connected)>1:
            drawn.append(net);r.labelled.pop(net,None)
    for net in drawn:
        # Discard isolated noise fragments, even when their source root had the
        # same name. Only the conductor connected to the actual reviewed pins is exported.
        connected=r.connected_cells(net,{r.pins[net][0][0]})
        r.edges[net]={edge for edge in r.edges[net] if set(edge)<=connected}
        segs = r.segments(net)
        if not segs:
            continue
        longest = max(segs, key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
        for a, b in segs:
            alias = ''
            ax = ay = 0
            if (a, b) == longest and (named_aliases is None or net in named_aliases):
                alias = net
                ax, ay = (a[0] + b[0]) // 2 * r.grid, (a[1] + b[1]) // 2 * r.grid
            out.append((a[0] * r.grid, a[1] * r.grid, b[0] * r.grid, b[1] * r.grid, alias, ax, ay))
            segment_nets.append(net)
    stubs = 0
    for net, pins in r.labelled.items():
        from .orcad_source_wires import real_net_name
        named=net in named_aliases if named_aliases is not None else real_net_name(net)
        if require_wires and (len(r.pins[net])!=1 or not (named or net in observed_stub_nets)):continue
        for h, d, grid, (hx, hy) in pins:
            length=2 if require_wires else r.stub
            if require_wires and any((h[0]+d[0]*k,h[1]+d[1]*k) in r.blocked or
                    r.owner.get((h[0]+d[0]*k,h[1]+d[1]*k),net)!=net or
                    r.occ.get((h[0]+d[0]*k,h[1]+d[1]*k),(net,))[0]!=net for k in range(1,length+1)):
                from .engine import OperationError
                raise OperationError('Visible wire routing incomplete: named singleton stub blocked for '+net)
            ex, ey = hx + d[0] * length * r.grid, hy + d[1] * length * r.grid
            out.append((hx, hy, ex, ey, net if named_aliases is None or net in named_aliases else '', ex, ey))
            segment_nets.append(net)
            stubs += 1
    crossings = sum(1 for o in r.occ.values() if o[1] == 'C')
    unrouted = {net: len(pins) for net, pins in r.labelled.items() if len(r.pins[net]) > 1}
    observed_ports=[list(w[2:4]) for w,net in zip(out,segment_nets) if net in observed_stub_nets and len(r.pins[net])==1 and not w[4]]
    summary = {'wired_nets': len(wired), 'labelled_pins': stubs, 'crossings': crossings,
               'observed_open_stub_ports':observed_ports,
               'labelled_nets': stubs if require_wires else len([n for n in r.labelled if n not in wired]),
               'named_singleton_stubs':sum(bool(w[4]) and len(r.pins[n])==1 for w,n in zip(out,segment_nets)) if require_wires else 0,
               'pruned_nonterminal_unit_edges':pruned,
               'unrouted_nets': unrouted,
               'singleton_pins': sum(len(pins) for net, pins in r.labelled.items() if len(r.pins[net]) == 1),
               'all_connections_wired': not unrouted}
    if source_report is not None:
        r.edges={net:edges for net,edges in r.edges.items() if net in drawn}
        # Record every unit edge absent from the measured geometry, then merge
        # those units into inspectable straight inferred segments.
        inferred=[]
        for net,edges in r.edges.items():
            observed=source_edges.get(net,set())
            r.edges[net]=edges-observed
            inferred += [{'net':net,'a':[a[0]*r.grid,a[1]*r.grid],'b':[b[0]*r.grid,b[1]*r.grid],
                          'source':'inferred_manhattan','reason':'source geometry missing, conflicting or not at a placed terminal'}
                         for a,b in r.segments(net)]
            r.edges[net]=edges
        for wire in out:
            if any((wire[0],wire[1])==(p[0][0]*r.grid,p[0][1]*r.grid) for pins in r.labelled.values() for p in pins):
                inferred.append({'a':list(wire[:2]),'b':list(wire[2:4]),'source':'isolated_terminal_stub','reason':'reviewed singleton has no connected partner'})
        source_report['inferred_segments']=inferred
        source_report['retained_source_unit_edges']=sum(len(edges & source_edges.get(net,set())) for net,edges in r.edges.items())
        source_report['native_wire_segments']=[{'a':list(w[:2]),'b':list(w[2:4]),'net':net} for w,net in zip(out,segment_nets)]
        junctions=[]
        for net,edges in r.edges.items():
            adjacent={}
            for edge in edges:
                a,b=tuple(edge);adjacent.setdefault(a,set()).add(b);adjacent.setdefault(b,set()).add(a)
            for point,neighbors in adjacent.items():
                if len(neighbors)<3:continue
                if point in r.source_crossings:continue
                at=[point[0]*r.grid,point[1]*r.grid]
                observed=any(j['net']==net and tuple(j['at'])==tuple(at) for j in source_report['source_junctions'])
                junctions.append({'at':at,'net':net,'degree':len(neighbors),'source':'observed_junction' if observed else 'inferred_routing_junction'})
        source_report['exported_junctions']=junctions
        for observed in source_report['source_junctions']:
            if require_wires:continue  # native dots require actual degree >= 3
            if observed['kind']!='junction' or any(j['at']==list(observed['at']) for j in junctions):continue
            x,y=observed['at']
            if (x//r.grid,y//r.grid) in r.source_crossings:continue
            touches=[s for s in source_report['native_wire_segments'] if s['net']==observed['net'] and
                     min(s['a'][0],s['b'][0])<=x<=max(s['a'][0],s['b'][0]) and
                     min(s['a'][1],s['b'][1])<=y<=max(s['a'][1],s['b'][1]) and
                     (s['a'][0]==s['b'][0]==x or s['a'][1]==s['b'][1]==y)]
            if touches:junctions.append({'at':[x,y],'net':observed['net'],'source':'observed_dot','degree':len(touches)})
        summary['source_reconstruction']=source_report
    if require_wires and unrouted:
        from .engine import OperationError
        raise OperationError('Visible wire routing incomplete for: ' + ', '.join(sorted(unrouted)) + '. Review the pin positions; no label-only fallback was exported.')
    if require_wires:
        from .orcad_wire_gaps import endpoints
        check=endpoints({**page,'wires':[list(w[:4]) for w in out],
                         'observed_ports':observed_ports,'aliases':[{'name':w[4],'x':w[5],'y':w[6]} for w in out if w[4]]},valid_aliases=named_aliases or ())
        summary['loose_wire_ends']=check['free_end_count']
        summary['unlabelled_loose_ends']=check['free_end_count']
        if not check['passed']:
            from .engine import OperationError
            raise OperationError('Visible wire routing incomplete: non-terminal leaf remains before native write')
    return out, summary


def verify_visible_wires(page, pin_net):
    """Check physical wire continuity without using aliases to join disconnected stubs.

    Endpoints and T junctions connect; an interior crossing of two wires does not.
    This is independent of the router and operates on the reopened Capture drawing.
    """
    wires = page['wires']
    parent = list(range(len(wires)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def on(point, wire):
        x, y = point
        x1, y1, x2, y2 = wire
        return (x1 == x2 == x and min(y1, y2) <= y <= max(y1, y2) or
                y1 == y2 == y and min(x1, x2) <= x <= max(x1, x2))

    for i, a in enumerate(wires):
        for j in range(i):
            b = wires[j]
            if (any(on(p, b) for p in (a[:2], a[2:])) or any(on(p, a) for p in (b[:2], b[2:]))
                    or any(on(p,a) and on(p,b) for p in page.get('junctions',[]))):
                parent[root(i)] = root(j)
    locations = {}
    for part in page['parts']:
        for pin in part['pins']:
            key = (part['base'], str(pin['number']))
            locations.setdefault(key, []).append((pin['hx'], pin['hy']))
    groups = {}
    missing = []
    by_net = {}
    net_sizes={}
    for net in pin_net.values():net_sizes[net]=net_sizes.get(net,0)+1
    for key, net in pin_net.items():
        hits = {root(i) for point in locations.get(key, ()) for i, wire in enumerate(wires) if on(point, wire)}
        if not hits and (net_sizes[net]>1 or key not in locations):
            missing.append(key)
        by_net.setdefault(net, []).append((key, hits))
        for hit in hits:
            groups.setdefault(hit, set()).add(net)
    disconnected = [net for net, pins in by_net.items()
                    if len(pins) > 1 and not set.intersection(*(hits for _, hits in pins))]
    shorts = [sorted(nets) for nets in groups.values() if len(nets) > 1]
    return {'passed': not (missing or disconnected or shorts),
            'multi_pin_nets': sum(len(pins) > 1 for pins in by_net.values()),
            'wire_segments': len(wires), 'missing_wire_pins': sorted(missing),
            'disconnected_nets': sorted(disconnected), 'shorted_nets': shorts}
