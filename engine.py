"""Ядро MathBoard: язык сценариев, безопасные выражения, анимации (без GUI)."""
import ast, math, re
import numpy as np

PALETTE = {"blue": "#58C4DD", "yellow": "#F7D96F", "red": "#FC6255", "green": "#83C167",
           "teal": "#5CD0B3", "purple": "#9A72AC", "orange": "#FF862F", "white": "#E8EAF0",
           "gray": "#8B93A7", "pink": "#D147BD"}
COMMANDS = {"axes", "text", "tex", "plot", "line", "arrow", "circle", "point", "wait", "clear",
            "pause", "fadeout", "morph", "move", "view", "heading", "box", "poly", "angle", "rightangle", "tick", "tri"}
DUR = {"axes": 1.0, "text": 0.9, "tex": 1.0, "plot": 2.0, "line": 1.0, "arrow": 1.0, "circle": 1.0,
       "point": 0.5, "clear": 0.6, "fadeout": 0.6, "morph": 1.5, "move": 1.2, "view": 0, "heading": 0.9, "box": 0.7, "poly": 1.2, "angle": 0.6, "rightangle": 0.4, "tick": 0.3, "tri": 1.2}


# ---------- безопасные выражения (numpy) ----------
_FN = {k: getattr(np, v) for k, v in dict(sin="sin", cos="cos", tan="tan", sqrt="sqrt", abs="abs", exp="exp",
       log="log", ln="log", atan="arctan", sinh="sinh", cosh="cosh", tanh="tanh").items()}
_OK = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Constant, ast.Load,
       ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd)


def compile_expr(src):
    tree = ast.parse(str(src).replace("^", "**"), mode="eval")
    for n in ast.walk(tree):
        bad = (not isinstance(n, _OK)
               or (isinstance(n, ast.Constant) and not isinstance(n.value, (int, float)))
               or (isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in _FN))
               or (isinstance(n, ast.Name) and n.id not in _FN and n.id not in ("x", "pi", "e")))
        if bad:
            raise ValueError(f"недопустимое выражение: {src}")
    code = compile(tree, "<expr>", "eval")
    env = {**_FN, "pi": math.pi, "e": math.e}

    def f(x):
        with np.errstate(all="ignore"):
            return np.asarray(eval(code, {"__builtins__": {}}, {**env, "x": x}), float) * np.ones_like(x)
    return f


# ---------- парсер ----------
class LessonError(Exception):
    def __init__(self, line, msg):
        super().__init__(f"строка {line}: {msg}")


_TOK = re.compile(r'''#.*|(?:\w+=)?"[^"]*"|(?:\w+=)?'[^']*'|\S+''')
_PAIR = re.compile(r'^-?\d+(\.\d+)?,-?\d+(\.\d+)?$')


def _unq(t):
    return t[1:-1] if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0] else t


def _val(t):
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        return t[1:-1]          # строка в кавычках остаётся строкой (иначе "7" стало бы 7.0)
    if _PAIR.match(t):
        a, b = t.split(",")
        return [float(a), float(b)]
    try:
        return float(t)
    except ValueError:
        return t


def parse(src):
    blocks, title = [[]], "Урок"
    for n, raw in enumerate(src.splitlines(), 1):
        toks = _TOK.findall(raw)
        if toks and toks[-1].startswith("#"):
            toks.pop()
        toks = [t for t in toks if not t.startswith("#")] if toks and toks[0].startswith("#") else toks
        if not toks:
            continue
        par = toks[0] == "&"                       # «&» — запустить одновременно с предыдущей
        if par:
            toks = toks[1:]
        if not toks:
            raise LessonError(n, "после & нет команды")
        op, rest = toks[0], toks[1:]
        if op == "title":
            title = _unq(rest[0]) if rest else title
        elif op == "pause":
            blocks.append([])
        elif op in COMMANDS:
            args, kw = [], {}
            for t in rest:
                m = re.match(r"^(\w+)=(.*)$", t, re.S) if t[0] not in "\"'" else None
                if m:
                    kw[m[1]] = _val(m[2])
                else:
                    args.append(_val(t))
            if op == "tri":                     # трикутник одной строкой: контур + вершины + подписи + позначки рівних сторін
                try:
                    blocks[-1].extend(_expand_tri(args, kw, par))
                except Exception as ex:
                    raise LessonError(n, str(ex))
                continue
            cmd = {"op": op, "args": args, "kw": kw, "par": par}
            try:
                check(cmd)
            except Exception as e:
                raise LessonError(n, str(e))
            blocks[-1].append(cmd)
        else:
            raise LessonError(n, f"неизвестная команда '{op}'")
    return {"title": title, "blocks": [b for b in blocks if b]}


def check(c):
    op, a = c["op"], c["args"]
    need = {"axes": 2, "text": 2, "tex": 2, "plot": 1, "line": 2, "arrow": 2, "circle": 2, "point": 1,
            "wait": 1, "fadeout": 1, "morph": 2, "move": 2, "view": 2, "heading": 1, "box": 2, "poly": 3, "angle": 3, "rightangle": 3, "tick": 2}.get(op, 0)
    if len(a) < need:
        raise ValueError(f"'{op}' требует аргументов: {need}")
    if op in ("plot", "morph"):
        compile_expr(a[-1] if op == "morph" else a[0])


# ---------- сцена и анимации ----------
def smooth(t):
    """Плавность как в Manim (сигмоида)."""
    t = min(1.0, max(0.0, t))
    s = lambda v: 1 / (1 + math.exp(-10 * (v - 0.5)))
    return (s(t) - s(0)) / (s(1) - s(0))


class Obj:
    def __init__(self, c):
        self.op, self.a, self.kw = c["op"], c["args"], c["kw"]
        self.id = self.kw.get("id")
        col = self.kw.get("color", "white")
        self.color = PALETTE.get(col, col)
        self.vis, self.dead, self.reveal, self.alpha = False, False, 0.0, 1.0
        self.pos = list({"text": 1, "tex": 1}.get(self.op) and self.a[1] or
                        (self.a[0] if self.op in ("point", "circle") else [0, 0]))
        self.f = compile_expr(self.a[0]) if self.op == "plot" else None
        self.f2, self.m = None, 0.0


class Scene:
    def __init__(self):
        self.reset()

    def reset(self):
        self.objs, self.anims, self.view = [], [], (-8.0, 8.0, -4.5, 4.5)

    def _find(self, i):
        return next((o for o in reversed(self.objs) if o.id == i and not o.dead), None)

    def play_block(self, cmds, now, instant=False):
        prev, end = now, now
        for c in cmds:
            op, a, kw = c["op"], c["args"], c["kw"]
            d = 0.0 if instant else 1000 * (a[0] if op == "wait" else kw.get("time", DUR.get(op, 1)))
            start = prev if c["par"] else end
            prev = start
            end = max(end, start + d) if c["par"] else start + d
            if op == "wait":
                continue
            self._plan(c, op, a, start, d)
        self.tick(now)

    def _add(self, start, d, fn):
        self.anims.append((start, d, fn))

    def _plan(self, c, op, a, start, d):
        if op in ("axes", "text", "tex", "plot", "line", "arrow", "circle", "point", "heading", "box", "poly", "angle", "rightangle", "tick"):
            o = Obj(c)
            v = (a[0][0], a[0][1], a[1][0], a[1][1]) if op == "axes" else None
            self.objs.append(o)

            def grow(p, o=o, v=v):
                o.vis, o.reveal = True, p
                if v:
                    self.view = v
            self._add(start, d, grow)
            return
        if op == "view":
            v = (a[0][0], a[0][1], a[1][0], a[1][1])
            self._add(start, 0.0, lambda p: setattr(self, "view", v))
            return
        if op == "clear":
            targets = list(self.objs)

            def fade(p):
                for o in targets:
                    o.alpha = 1 - p
                    o.dead = o.dead or p >= 1
            self._add(start, d, fade)
            return
        o = self._find(a[0] if op != "move" else a[0]) if isinstance(a[0], str) else None
        if o is None:
            return
        if op == "fadeout":
            def fo(p):
                o.alpha = 1 - p
                o.dead = p >= 1
            self._add(start, d, fo)
        elif op == "morph" and o.op == "plot":
            f2, st = compile_expr(a[1]), {}

            def mo(p):
                o.f2, o.m = f2, p
                if p >= 1:
                    o.f, o.m = f2, 0.0
            self._add(start, d, mo)
        elif op == "move":
            st = {}

            def mv(p):
                st.setdefault("o", list(o.pos))
                o.pos = [st["o"][0] + (a[1][0] - st["o"][0]) * p, st["o"][1] + (a[1][1] - st["o"][1]) * p]
            self._add(start, d, mv)

    def tick(self, now):
        keep = []
        for start, d, fn in sorted(self.anims, key=lambda x: x[0]):
            if now < start:
                keep.append((start, d, fn))
                continue
            p = 1.0 if d <= 0 else min(1.0, (now - start) / d)
            fn(smooth(p))
            if p < 1:
                keep.append((start, d, fn))
        self.anims = keep
        self.objs = [o for o in self.objs if not o.dead]
        return bool(keep)


if __name__ == "__main__":      # быстрая самопроверка:  python engine.py lesson.mth
    import sys
    print(parse(open(sys.argv[1], encoding="utf-8").read())["title"], "— сценарий корректен")


def _expand_tri(args, kw, par):
    pts = [a for a in args if isinstance(a, list)][:3]
    if len(pts) < 3:
        raise ValueError("tri: нужно три вершины в виде x,y")
    names = [s.strip() for s in str(kw.get("names", "A,B,C")).split(",")]
    ticks = ([int(float(t)) for t in str(kw.get("ticks", "0,0,0")).split(",")] + [0, 0, 0])[:3]   # стороны P1P2, P2P3, P3P1
    col = kw.get("color", "white")
    out = [{"op": "poly", "args": pts, "kw": {**{k: kw[k] for k in ("color", "fill", "dash", "width") if k in kw}, "time": kw.get("time", 1.2)}, "par": par}]
    cx, cy = sum(p[0] for p in pts) / 3, sum(p[1] for p in pts) / 3
    if names != [""]:
        for p, nm in zip(pts, names):
            dx, dy = p[0] - cx, p[1] - cy
            d = math.hypot(dx, dy) or 1
            out.append({"op": "point", "args": [p], "kw": {"label": nm, "ldx": round(dx / d * .42, 2), "ldy": round(dy / d * .42, 2), "color": col, "time": .3}, "par": True})
    first = True
    for i, t in enumerate(ticks):
        if t > 0:
            out.append({"op": "tick", "args": [pts[i], pts[(i + 1) % 3]], "kw": {"n": t, "color": "yellow", "time": .3}, "par": not first})
            first = False
    return out


# ---------- для веб-версии ----------
def to_js(src):
    """Python-выражение (уже проверенное белым списком) -> безопасный JS."""
    compile_expr(src)
    tree = ast.parse(str(src).replace("^", "**"), mode="eval")
    ops = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}

    def j(n):
        if isinstance(n, ast.Expression): return j(n.body)
        if isinstance(n, ast.Constant): return repr(float(n.value))
        if isinstance(n, ast.Name): return {"pi": "Math.PI", "e": "Math.E"}.get(n.id, n.id)
        if isinstance(n, ast.UnaryOp): return "(" + ("-" if isinstance(n.op, ast.USub) else "+") + j(n.operand) + ")"
        if isinstance(n, ast.BinOp):
            l, r = j(n.left), j(n.right)
            return f"Math.pow({l},{r})" if isinstance(n.op, ast.Pow) else "(" + l + ops[type(n.op)] + r + ")"
        if isinstance(n, ast.Call):
            return "Math." + {"ln": "log"}.get(n.func.id, n.func.id) + "(" + ",".join(j(x) for x in n.args) + ")"
        raise ValueError("недопустимое выражение")
    return j(tree)


def _text_path(s):
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties, findfont, get_font
    for fam in ("STIXGeneral", "DejaVu Serif"):           # шрифт с засечками и кириллицей
        prop = FontProperties(family=fam)
        cmap = get_font(findfont(prop)).get_charmap()
        if all(ord(ch) in cmap for ch in s if not ch.isspace()):
            break
    return TextPath((0, 0), s, size=400, prop=prop)


def glyph(s, kind):
    """Контуры текста/формулы в SVG-формате (кегль 400, y вниз) + длины контуров для эффекта Write."""
    import matplotlib
    matplotlib.rcParams["mathtext.fontset"] = "cm"
    from matplotlib.textpath import TextPath
    tp = TextPath((0, 0), f"${s}$", size=400) if kind == "tex" else _text_path(s)
    out, cur, L, last, start, xs = [], [], 0.0, (0, 0), (0, 0), []
    dist = lambda a, b: math.hypot(a[0] - b[0], a[1] - b[1])
    for v, c in tp.iter_segments(simplify=False):
        v = [float(t) for t in v]
        P = [(v[i], -v[i + 1]) for i in range(0, len(v) - 1, 2)]
        f = lambda *q: " ".join(f"{x:.1f} {y:.1f}" for x, y in q)
        if c == 1:
            cur, L, start, last = [f"M{f(P[0])}"], 0.0, P[0], P[0]
        elif c == 2:
            cur.append(f"L{f(P[0])}"); L += dist(last, P[0]); last = P[0]
        elif c == 3:
            cur.append(f"Q{f(P[0], P[1])}"); L += dist(last, P[0]) + dist(P[0], P[1]); last = P[1]
        elif c == 4:
            cur.append(f"C{f(P[0], P[1], P[2])}"); L += dist(last, P[0]) + dist(P[0], P[1]) + dist(P[1], P[2]); last = P[2]
        elif c == 79:
            cur.append("Z"); L += dist(last, start)
            if L > 0: out.append({"d": " ".join(cur), "l": round(L, 1)})
            continue
        xs += [p[0] for p in P]
    return {"c": out, "b": [round(min(xs), 1), round(max(xs), 1)] if xs else [0, 0]}


def prep(script):
    """Добавляет в сценарий всё, что нужно браузеру: контуры букв и формулы функций."""
    G = {}
    for b in script["blocks"]:
        for c in b:
            a, op = c["args"], c["op"]
            if op in ("text", "tex", "heading"):
                kind = "tex" if op == "tex" else "text"
                key = f"{kind}|{a[0]}"
                if key not in G: G[key] = glyph(str(a[0]), kind)
                c["g"] = key
            if op == "plot": c["js"] = to_js(a[0])
            if op == "morph": c["js"] = to_js(a[1])
            if op in ("point", "angle") and "label" in c["kw"]:
                key = "tex|" + str(c["kw"]["label"])
                if key not in G: G[key] = glyph(str(c["kw"]["label"]), "tex")
                c["lg"] = key
    script["glyphs"] = G
    return script
