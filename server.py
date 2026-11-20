"""MathBoard Web.  Запуск:  python server.py monomials.mth
Учитель открывает ссылку с ключом, ученики — обычную ссылку (в браузере планшета, ничего ставить не надо)."""
import atexit, json, os, re, secrets, shutil, socket, subprocess, sys, threading, time
from pathlib import Path
from aiohttp import web, WSMsgType
from engine import parse, prep, LessonError

HERE = Path(__file__).parent
PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "monomials.mth")
PORT = int(os.environ.get("PORT", 8080))                        # в облаке порт выдаёт хостинг
KEY = os.environ.get("TEACHER_KEY") or secrets.token_urlsafe(6)   # в облаке ключ учителя постоянный
CLOUD = bool(os.environ.get("TEACHER_KEY"))                        # ключ задан -> запуск на сервере, туннели не нужны
S = {"script": {}, "block": -1, "strokes": {}, "draw_ok": True}
clients, roles, owners = set(), {}, {}


def load():
    try:
        S["script"] = prep(parse(PATH.read_text(encoding="utf-8")))
        return ""
    except (LessonError, OSError, ValueError) as e:
        return str(e)


def init_msg(role, err=""):
    return json.dumps({"type": "init", "role": role, "script": S["script"], "block": S["block"],
                       "strokes": S["strokes"], "draw_ok": S["draw_ok"], "err": err}, ensure_ascii=False)


async def send_all(msg, skip=None):
    data = json.dumps(msg, ensure_ascii=False)
    for ws in list(clients):
        if ws is not skip and not ws.closed:
            await ws.send_str(data)


async def count():
    await send_all({"type": "count", "n": sum(1 for r in roles.values() if r == "student")})


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    role = "teacher" if request.query.get("key") == KEY else "student"
    clients.add(ws); roles[ws] = role
    await ws.send_str(init_msg(role)); await count()
    nb = lambda: len(S["script"]["blocks"])
    try:
        async for m in ws:
            if m.type != WSMsgType.TEXT:
                continue
            d = json.loads(m.data); t = d.get("type"); teacher = role == "teacher"
            if t == "seg" and (teacher or S["draw_ok"]):
                st = S["strokes"].setdefault(d["id"], {"color": d["color"], "pts": []})
                owners.setdefault(d["id"], ws); st["pts"] += d["pts"]
                await send_all(d, skip=ws)
            elif t == "undo" and (teacher or owners.get(d["id"]) is ws):
                S["strokes"].pop(d["id"], None)
                await send_all({"type": "rm", "id": d["id"]}, skip=ws)
            elif teacher and t in ("next", "prev", "reset"):
                old = S["block"]
                S["block"] = {"next": min(old + 1, nb() - 1), "prev": max(old - 1, -1), "reset": -1}[t]
                await send_all({"type": "goto", "block": S["block"], "animate": t == "next" and S["block"] != old})
            elif teacher and t == "clear":
                S["strokes"].clear(); await send_all({"type": "clear"})
            elif teacher and t == "toggle":
                S["draw_ok"] = not S["draw_ok"]; await send_all({"type": "draw_ok", "v": S["draw_ok"]})
            elif teacher and t == "reload":
                err = load(); S["block"] = min(S["block"], nb() - 1)
                for c in list(clients):
                    await c.send_str(init_msg(roles[c], err))
    finally:
        clients.discard(ws); roles.pop(ws, None)
        await count()
    return ws


async def index(_):
    return web.FileResponse(HERE / "index.html", headers={"Cache-Control": "no-store"})


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
    except OSError:
        return "localhost"


def start_tunnel():
    """Публичная https-ссылка. Порядок: ngrok (если установлен) -> cloudflared -> запасной localhost.run через ssh."""
    found = threading.Event()

    def run(cmd, pattern, name):
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="ignore")
        except OSError as e:
            print(f"  [{name}] не запустился: {e}")
            return
        atexit.register(proc.terminate)
        for line in proc.stdout:
            line = line.strip()
            if name == "ssh" or any(w in line.lower() for w in ("err", "fail", "timeout", "refused", "denied")):
                print(f"  [{name}] {line[:170]}")
            urls = [u for u in re.findall(pattern, line) if not u.startswith("https://api.")]
            if urls and not found.is_set():
                found.set()
                print(f"\n  ★ ССЫЛКА ДЛЯ УЧЕНИКА (из любого города): {urls[0]}/\n")

    ng = shutil.which("ngrok")
    cf = shutil.which("cloudflared") or next((str(p) for p in (HERE / "cloudflared.exe", Path("cloudflared.exe")) if p.exists()), None)

    def main_tunnel():
        for n in range(3):
            if ng:
                run([ng, "http", str(PORT), "--log", "stdout"], r'url=(https://[-a-z0-9.]+)', "ngrok")
            else:
                run([cf, "tunnel", "--url", f"http://localhost:{PORT}"], r"https://[-a-z0-9]+\.trycloudflare\.com", "cloudflared")
            if found.is_set():
                return
            print(f"  [{'ngrok' if ng else 'cloudflared'}] попытка {n + 1} из 3 не удалась" + (", повторяю…" if n < 2 else ""))
            time.sleep(3)
    if ng or cf:
        threading.Thread(target=main_tunnel, daemon=True).start()

    def fallback():
        if (ng or cf) and found.wait(60):
            return
        ssh = shutil.which("ssh")
        if not ssh:
            print("  Публичная ссылка не создана. Ученики из вашей Wi-Fi сети могут зайти по адресу выше.")
            return
        print("  Основной туннель не поднялся — пробую запасной (localhost.run)…")
        for n in range(20):                      # если туннель оборвётся — переподключаемся и выдаём новую ссылку
            found.clear()
            run([ssh, "-T", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
                 "-o", "ExitOnForwardFailure=yes", "-R", f"80:localhost:{PORT}", "nokey@localhost.run"],
                r"https://[-a-z0-9]+\.lhr\.life", "ssh")
            print("  [ssh] туннель оборвался, переподключаюсь… (ученику понадобится НОВАЯ ссылка)")
            time.sleep(3)
    threading.Thread(target=fallback, daemon=True).start()


if __name__ == "__main__":
    err = load()
    if err:
        sys.exit("Ошибка сценария: " + err)
    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/ws", ws_handler)])
    print(f"\n  Учитель (открыть у себя): http://localhost:{PORT}/?key={KEY}")
    print(f"  Ученики в вашей Wi-Fi сети: http://{lan_ip()}:{PORT}/")
    if not CLOUD:
        start_tunnel()
    web.run_app(app, host="0.0.0.0", port=PORT, print=None)
