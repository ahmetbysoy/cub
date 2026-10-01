#!/usr/bin/env python3
"""
CubeCraft mini mod-server (prototip)

Termux (Ubuntu/proot) içinde çalışır; Frida ile oyuna bağlanır, tarayıcıdan
kullanılabilecek küçük bir kontrol paneli sunar:

    python3 server.py --host 127.0.0.1:27042 --target Gadget
    python3 server.py --usb --target com.cww.cubecraft

Panel: http://127.0.0.1:8080

Not: Hedef cihaz/uygulama üzerinde Frida erişimi gerekir:
  * root'lu cihaz  → frida-server çalışıyor olmalı (127.0.0.1:27042)
  * root'suz cihaz → APK'ya gömülü frida-gadget "listen" modunda (Gadget süreci)
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

try:
    import frida
except ImportError:  # pragma: no cover
    frida = None

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_JS = os.path.join(HERE, "agent", "il2cpp_agent.js")
DEFAULT_BRIDGE = os.path.join(HERE, "node_modules", "frida-il2cpp-bridge", "dist", "index.js")


# --------------------------------------------------------------------------- #
# Frida köprüsü
# --------------------------------------------------------------------------- #
class Bridge:
    def __init__(self, host: str | None, usb: bool, target: str, bridge_js: str, spawn: bool):
        self.host = host
        self.usb = usb
        self.target = target
        self.bridge_js = bridge_js
        self.spawn = spawn
        self.lock = threading.Lock()
        self.logs: list[dict] = []
        self.script = None
        self.session = None
        self.device = None
        self.error: str | None = None

    # -- bağlantı ---------------------------------------------------------- #
    def connect(self) -> None:
        if frida is None:
            self.error = "frida kurulu değil: pip install frida"
            return
        try:
            if self.host:
                device = frida.get_device_manager().add_remote_device(self.host)
            elif self.usb:
                device = frida.get_usb_device(timeout=10)
            else:
                device = frida.get_local_device()
            self.device = device

            if self.spawn:
                pid = device.spawn([self.target])
                self.session = device.attach(pid)
                device.resume(pid)
            else:
                self.session = device.attach(self.target)

            source = self._compose_script()
            script = self.session.create_script(source)
            script.on("message", self._on_message)
            script.on("destroyed", lambda: self._add_log("warn", "ajan oturumu kapandı"))
            script.load()
            self.script = script
            self._add_log("info", "bağlandı: %s (%s)" % (self.target, device.name if hasattr(device, "name") else "?"))
        except Exception as exc:  # noqa: BLE001
            self.error = "%s: %s" % (type(exc).__name__, exc)
            self._add_log("error", "bağlantı hatası → " + self.error)

    def _compose_script(self) -> str:
        if not os.path.exists(self.bridge_js):
            raise FileNotFoundError(
                "frida-il2cpp-bridge bulunamadı: %s\n"
                "  npm i frida-il2cpp-bridge  (veya --bridge ile yol ver)" % self.bridge_js
            )
        with open(self.bridge_js, "r", encoding="utf-8") as fh:
            bridge = fh.read()
        with open(AGENT_JS, "r", encoding="utf-8") as fh:
            agent = fh.read()
        # CommonJS kalıntılarına karşı küçük bir güvence
        guard = "if (typeof exports === 'undefined') { var exports = {}; }\n"
        return guard + bridge + "\n;\n" + agent

    # -- mesajlar ---------------------------------------------------------- #
    def _add_log(self, level: str, msg: str) -> None:
        self.logs.append({"ts": int(time.time() * 1000), "level": level, "msg": msg})
        if len(self.logs) > 500:
            del self.logs[:250]
        print("[%s] %s" % (level, msg), flush=True)

    def _on_message(self, message: dict, data) -> None:
        if message.get("type") == "send":
            payload = message.get("payload") or {}
            if isinstance(payload, dict) and payload.get("type") == "log":
                self._add_log(payload.get("level", "info"), payload.get("msg", ""))
            else:
                self._add_log("info", json.dumps(payload, ensure_ascii=False)[:500])
        elif message.get("type") == "error":
            self._add_log("error", (message.get("description") or "ajan hatası") + "\n" + (message.get("stack") or ""))

    # -- rpc --------------------------------------------------------------- #
    def call(self, name: str, *args):
        if self.script is None:
            raise RuntimeError("bağlantı yok" + ((": " + self.error) if self.error else ""))
        with self.lock:
            fn = getattr(self.script.exports, name)
            return fn(*args)

    def status(self) -> dict:
        info = {
            "connected": self.script is not None,
            "target": self.target,
            "host": self.host or ("usb" if self.usb else "local"),
            "error": self.error,
            "logs": len(self.logs),
        }
        if self.script is not None:
            try:
                info.update(self.call("ping"))
            except Exception as exc:  # noqa: BLE001
                info["ping_error"] = str(exc)
        return info


BRIDGE: Bridge | None = None


# --------------------------------------------------------------------------- #
# HTTP katmanı
# --------------------------------------------------------------------------- #
PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CubeCraft mini panel</title>
<style>
 :root{color-scheme:dark}
 body{font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#12141a;color:#e8eaf0}
 header{padding:14px 18px;background:#1b1e27;border-bottom:1px solid #2a2f3d;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
 h1{font-size:16px;margin:0}
 .pill{padding:3px 10px;border-radius:99px;background:#252a36;font-size:12px}
 .pill.ok{background:#1d3a2a;color:#7ee2a8}.pill.bad{background:#3a1d22;color:#ff9aa8}
 main{padding:18px;max-width:960px;margin:0 auto}
 section{margin-bottom:22px;background:#171a22;border:1px solid #262b38;border-radius:12px;padding:14px}
 h2{font-size:14px;margin:0 0 10px;color:#9fb0d0;text-transform:uppercase;letter-spacing:.06em}
 input,select,button{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid #333a4a;background:#10131a;color:#e8eaf0}
 button{background:#2b4cff;border-color:#2b4cff;cursor:pointer}
 button.alt{background:#252a36;border-color:#333a4a}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #232836}
 tr:hover td{background:#1c202b}
 code{background:#0f1219;padding:1px 5px;border-radius:5px}
 #log{height:240px;overflow:auto;background:#0d1017;border-radius:8px;padding:8px;font:12px/1.45 ui-monospace,Menlo,monospace;white-space:pre-wrap}
 .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
 .muted{color:#8b97ad}
</style></head>
<body>
<header>
  <h1>🧊 CubeCraft mini panel</h1>
  <span id="status" class="pill">bağlanıyor…</span>
  <button class="alt" onclick="refreshStatus()">Yenile</button>
</header>
<main>
  <section>
    <h2>Sınıf / metod ara</h2>
    <div class="row">
      <input id="q" placeholder="ör. Money, Gems, Save, Rewarded" style="flex:1;min-width:220px">
      <button onclick="search()">Ara</button>
    </div>
    <div id="results"></div>
  </section>
  <section>
    <h2>Aktif modlar</h2>
    <button class="alt" onclick="unwatchAll()">Tümünü kaldır</button>
    <div id="watches" class="muted">—</div>
  </section>
  <section>
    <h2>Log</h2>
    <label class="muted"><input type="checkbox" id="autoscroll" checked> otomatik kaydır</label>
    <div id="log"></div>
  </section>
</main>
<script>
let lastTs = 0;
const $ = (id) => document.getElementById(id);

async function api(path, opts) {
  const res = await fetch(path, opts);
  const txt = await res.text();
  try { return JSON.parse(txt); } catch (e) { return { raw: txt }; }
}

async function refreshStatus() {
  const s = await api('/api/status');
  const el = $('status');
  if (s.connected && !s.error) { el.className = 'pill ok'; el.textContent = `bağlı · Unity ${s.unityVersion || '?'} · ${s.classes || '?'} sınıf`; }
  else { el.className = 'pill bad'; el.textContent = 'bağlı değil' + (s.error ? ' — ' + s.error : ''); }
  loadWatches();
}

async function search() {
  const q = $('q').value.trim();
  const data = await api('/api/search?q=' + encodeURIComponent(q) + '&limit=60');
  if (data.error) { $('results').innerHTML = `<p class="muted">Hata: ${data.error}</p>`; return; }
  const rows = (data.classes || []).map(c =>
    `<tr><td><code>${c.namespace ? c.namespace + '.' : ''}${c.name}</code></td>` +
    `<td class="muted">${c.assembly}</td><td>${c.methods}</td><td>${c.fields}</td>` +
    `<td><button class="alt" onclick="showMethods('${c.assembly}','${c.namespace}','${c.name}')">metodlar</button></td></tr>`).join('');
  $('results').innerHTML = `<table><tr><th>Sınıf</th><th>Assembly</th><th>Metod</th><th>Alan</th><th></th></tr>${rows}</table>`;
}

async function showMethods(assembly, ns, name) {
  const data = await api(`/api/methods?assembly=${encodeURIComponent(assembly)}&namespace=${encodeURIComponent(ns)}&name=${encodeURIComponent(name)}`);
  if (data.error) { alert(data.error); return; }
  const rows = (data.methods || []).map(m =>
    `<tr><td><code>${m.name}</code></td><td>${m.parameterCount}</td><td>${m.isStatic ? 'static' : 'instance'}</td>` +
    `<td class="muted">${m.returnType}</td><td class="muted">${m.va}</td>` +
    `<td><button onclick="watch('${assembly}','${ns}','${name}','${m.name}',${m.parameterCount},'log')">izle</button> ` +
    `<button class="alt" onclick="watch('${assembly}','${ns}','${name}','${m.name}',${m.parameterCount},'const')">sabit</button> ` +
    `<button class="alt" onclick="watch('${assembly}','${ns}','${name}','${m.name}',${m.parameterCount},'multiply')">×N</button></td></tr>`).join('');
  $('results').innerHTML = `<h3><code>${ns ? ns + '.' : ''}${name}</code></h3>` +
    `<table><tr><th>Metod</th><th>Param</th><th>Tür</th><th>Dönüş</th><th>VA</th><th></th></tr>${rows}</table>`;
}

async function watch(assembly, ns, name, method, paramCount, mode) {
  const body = { assembly, namespace: ns, name, method, paramCount, mode };
  if (mode === 'const') { body.value = Number(prompt('Sabit değer (sayı):', '999999')); }
  if (mode === 'multiply') { body.factor = Number(prompt('Çarpan:', '10')); }
  const data = await api('/api/watch', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify(body)});
  if (data.error) alert(data.error);
  loadWatches();
}

async function loadWatches() {
  const data = await api('/api/watches');
  const list = data.watches || [];
  $('watches').innerHTML = list.length
    ? list.map(w => `<div class="row"><code>${w.label}</code><span class="pill">${w.mode}</span>` +
        `<button class="alt" onclick="unwatch('${w.id}')">kaldır</button></div>`).join('')
    : '<span class="muted">henüz mod yok — bir sınıf arayıp metodları listeleyin.</span>';
}

async function unwatch(id) {
  await api('/api/unwatch', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({id})});
  loadWatches();
}

async function unwatchAll() {
  await api('/api/unwatch_all', {method:'POST'});
  loadWatches();
}

async function pollLogs() {
  const data = await api('/api/logs?since=' + lastTs);
  const box = $('log');
  for (const entry of (data.logs || [])) {
    lastTs = Math.max(lastTs, entry.ts);
    const color = entry.level === 'error' ? '#ff9aa8' : (entry.level === 'warn' ? '#ffd479' : '#c8d3e8');
    box.insertAdjacentHTML('beforeend', `<div style="color:${color}">[${new Date(entry.ts).toLocaleTimeString()}] ${entry.msg}</div>`);
  }
  if ($('autoscroll').checked) box.scrollTop = box.scrollHeight;
}

refreshStatus();
setInterval(refreshStatus, 5000);
setInterval(pollLogs, 1500);
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "CubeCraftMiniPanel/0.1"

    # -- yardımcılar ------------------------------------------------------- #
    def _json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _guard(self, fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            self._json({"error": "%s: %s" % (type(exc).__name__, exc), "trace": traceback.format_exc()[-800:]}, 500)

    # -- yönlendirme ------------------------------------------------------- #
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        assert BRIDGE is not None

        if parsed.path in ("/", "/index.html"):
            return self._html(PAGE)

        if parsed.path == "/api/status":
            return self._json(BRIDGE.status())

        if parsed.path == "/api/logs":
            since = int(query.get("since", ["0"])[0])
            return self._json({"logs": [x for x in BRIDGE.logs if x["ts"] >= since]})

        if parsed.path == "/api/watches":
            return self._guard(lambda: self._json({"watches": BRIDGE.call("listWatches")}))

        if parsed.path == "/api/search":
            q = query.get("q", [""])[0]
            limit = int(query.get("limit", ["100"])[0])
            return self._guard(lambda: self._json({"classes": BRIDGE.call("searchClasses", q, limit)}))

        if parsed.path == "/api/methods":
            a = query.get("assembly", [None])[0]
            ns = query.get("namespace", [""])[0]
            name = query.get("name", [""])[0]
            return self._guard(lambda: self._json({"methods": BRIDGE.call("listMethods", a, ns, name)}))

        if parsed.path == "/api/fields":
            a = query.get("assembly", [None])[0]
            ns = query.get("namespace", [""])[0]
            name = query.get("name", [""])[0]
            return self._guard(lambda: self._json({"fields": BRIDGE.call("listFields", a, ns, name)}))

        return self._json({"error": "bilinmeyen yol: " + parsed.path}, 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        assert BRIDGE is not None
        payload = self._body()

        if parsed.path == "/api/watch":
            return self._guard(lambda: self._json(BRIDGE.call("watch", payload)))
        if parsed.path == "/api/unwatch":
            return self._guard(lambda: self._json(BRIDGE.call("unwatch", payload.get("id"))))
        if parsed.path == "/api/unwatch_all":
            return self._guard(lambda: self._json(BRIDGE.call("unwatchAll")))
        if parsed.path == "/api/invoke":
            return self._guard(lambda: self._json(BRIDGE.call("invoke", payload)))
        if parsed.path == "/api/field/read":
            return self._guard(lambda: self._json(BRIDGE.call("readField", payload)))
        if parsed.path == "/api/field/write":
            return self._guard(lambda: self._json(BRIDGE.call("writeField", payload)))
        if parsed.path == "/api/connect":
            return self._guard(lambda: (BRIDGE.connect(), self._json(BRIDGE.status()))[1])

        return self._json({"error": "bilinmeyen yol: " + parsed.path}, 404)

    def log_message(self, fmt: str, *args) -> None:  # sessiz
        pass


def main() -> None:
    global BRIDGE
    parser = argparse.ArgumentParser(description="CubeCraft mini mod-server")
    parser.add_argument("--host", help="cihaz adresi, ör. 127.0.0.1:27042 (gadget/frida-server)")
    parser.add_argument("--usb", action="store_true", help="USB ile bağlı cihazı kullan")
    parser.add_argument("--target", default="Gadget", help="süreç adı (gadget) veya paket adı (frida-server)")
    parser.add_argument("--spawn", action="store_true", help="uygulamayı başlatıp bağlan")
    parser.add_argument("--bridge", default=DEFAULT_BRIDGE, help="frida-il2cpp-bridge dist/index.js yolu")
    parser.add_argument("--port", type=int, default=8080, help="panel portu")
    parser.add_argument("--no-connect", action="store_true", help="başlangıçta bağlanma, panelden bağlan")
    args = parser.parse_args()

    if frida is None:
        print("Uyarı: 'frida' Python paketi yok → pip install frida", flush=True)

    BRIDGE = Bridge(host=args.host, usb=args.usb, target=args.target, bridge_js=args.bridge, spawn=args.spawn)
    if not args.no_connect:
        BRIDGE.connect()

    httpd = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print("Panel: http://127.0.0.1:%d  (hedef: %s)" % (args.port, args.target), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nkapatılıyor…", flush=True)


if __name__ == "__main__":
    main()
