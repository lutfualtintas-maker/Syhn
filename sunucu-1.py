#!/usr/bin/env python3
"""Asistan cihaz sunucusu (Termux). Yalnızca bu cihazdan erişilir (127.0.0.1)."""
import base64, html as htmlmod, json, os, re, shutil, subprocess, threading, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
HERE = os.path.dirname(os.path.abspath(__file__))
IZINLI = {f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"}
# GitHub Pages'ten kullanacaksan: ASISTAN_ORIGIN=https://kullanici.github.io python sunucu.py
IZINLI |= set(filter(None, os.environ.get("ASISTAN_ORIGIN", "").split(",")))
HOSTLAR = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
KEYS = {"oynat_durdur": 85, "oynat": 126, "duraklat": 127, "dur": 86, "sonraki": 87, "onceki": 88}


def calistir(*a):
    try:
        r = subprocess.run(a, capture_output=True, text=True, timeout=15)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def url_ac(u):
    if not re.match(r"^https?://", u):
        return False, "Yalnızca http/https adresleri açılır."
    if shutil.which("termux-open-url"):
        ok, o = calistir("termux-open-url", u)
    else:
        ok, o = calistir("am", "start", "-a", "android.intent.action.VIEW", "-d", u)
    return ok, ("Açıldı: " + u) if ok else ("Açılamadı: " + o[:120])


def yt_ilk_video(q):
    url = ("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q)
           + "&sp=EgIQAQ%3D%3D")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9"})
    html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")
    ids = re.findall(r'"videoId":"([\w-]{11})"', html)
    return ids[0] if ids else None


def youtube(q):
    q = q[:200]
    try:
        vid = yt_ilk_video(q)
    except Exception:
        vid = None
    if vid:
        return url_ac("https://www.youtube.com/watch?v=" + vid)
    return url_ac("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))


UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
      "Accept-Language": "tr-TR,tr;q=0.9"}


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=12).read().decode("utf-8", "ignore")


def ddg(q):
    h = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q))
    out = []
    for m in re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"', h):
        m = htmlmod.unescape(m)
        if "uddg=" in m:
            m = urllib.parse.unquote(m.split("uddg=")[1].split("&")[0])
        elif m.startswith("//"):
            m = "https:" + m
        out.append(m)
    return out


def bing(q):
    h = _get("https://www.bing.com/search?setlang=tr&q=" + urllib.parse.quote(q))
    out = []
    for m in re.findall(r'<li class="b_algo".*?<a href="([^"]+)"', h, re.S):
        m = htmlmod.unescape(m)
        mm = re.search(r"[?&]u=a1([A-Za-z0-9_-]+)", m)
        if mm:
            b = mm.group(1)
            b += "=" * (-len(b) % 4)
            try:
                m = base64.urlsafe_b64decode(b).decode()
            except Exception:
                pass
        out.append(m)
    return out


def ilk_sonuc(site, q):
    for fn in (ddg, bing):
        try:
            for u in fn(f"site:{site} {q}"):
                h = urllib.parse.urlparse(u).hostname or ""
                if u.startswith("http") and (h == site or h.endswith("." + site)):
                    return u
        except Exception:
            pass
    return None


def oynat_dene():
    if shutil.which("adb"):
        calistir("adb", "shell", "input", "keyevent", "126")


def site_video(site, q):
    site = site.lower().strip()
    site = site[4:] if site.startswith("www.") else site
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", site):
        return False, "Geçersiz site adı"
    u = ilk_sonuc(site, q[:200])
    if not u:
        return url_ac("https://www.google.com/search?q=" + urllib.parse.quote(f"site:{site} {q[:200]}"))
    ok, msg = url_ac(u)
    if ok:  # sayfa kendiliğinden oynatmazsa: en iyi çaba, medya "oynat" tuşu
        threading.Timer(7, oynat_dene).start()
    return ok, msg


def ses(v):
    ok, out = calistir("termux-volume")
    if not ok:
        return False, "termux-volume çalışmadı (Termux:API uygulaması ve paketi kurulu mu?)"
    try:
        m = next(x for x in json.loads(out) if x["stream"] == "music")
        mx, cur = m["max_volume"], m["volume"]
        if v == "artir":
            n = min(mx, cur + max(1, mx // 6))
        elif v == "azalt":
            n = max(0, cur - max(1, mx // 6))
        elif v == "sessiz":
            n = 0
        else:
            n = round(mx * max(0, min(100, int(v))) / 100)
    except Exception:
        return False, "Ses değeri anlaşılamadı"
    ok, o = calistir("termux-volume", "music", str(n))
    return ok, f"Ses {n}/{mx}" if ok else o[:120]


def medya(k):
    if k not in KEYS:
        return False, "Bilinmeyen medya komutu"
    if not shutil.which("adb"):
        return False, "adb kurulu değil (pkg install android-tools) ve kablosuz hata ayıklama bağlı olmalı"
    ok, o = calistir("adb", "shell", "input", "keyevent", str(KEYS[k]))
    return ok, ("Medya: " + k) if ok else ("adb hatası: " + o[:120])


def yap(d):
    a = d.get("a")
    if a == "url":
        return url_ac(str(d.get("u", "")))
    if a == "youtube":
        return youtube(str(d.get("q", "")))
    if a == "site":
        return site_video(str(d.get("s", "")), str(d.get("q", "")))
    if a == "ses":
        return ses(d.get("v"))
    if a == "medya":
        return medya(str(d.get("k", "")))
    return False, "Bilinmeyen komut"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors(self):
        o = self.headers.get("Origin")
        if o in IZINLI:
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Access-Control-Allow-Headers", "content-type")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Vary", "Origin")

    def _host_ok(self):
        return self.headers.get("Host", "") in HOSTLAR

    def _json(self, kod, d):
        b = json.dumps(d, ensure_ascii=False).encode()
        self.send_response(kod)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"ok": False, "msg": "Yasak"})
        p = self.path.split("?")[0]
        if p == "/durum":
            return self._json(200, {"ok": True, "msg": "Sunucu çalışıyor"})
        if p in ("/", "/asistan.html", "/index.html"):
            for ad in ("asistan.html", "index.html"):
                f = os.path.join(HERE, ad)
                if os.path.exists(f):
                    b = open(f, "rb").read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    return self.wfile.write(b)
        self._json(404, {"ok": False, "msg": "Bulunamadı"})

    def do_POST(self):
        o = self.headers.get("Origin")
        if not self._host_ok() or (o and o not in IZINLI):
            return self._json(403, {"ok": False, "msg": "Yasak"})
        if self.path != "/do":
            return self._json(404, {"ok": False, "msg": "Bulunamadı"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
            ok, msg = yap(d)
        except Exception as e:
            ok, msg = False, "Hata: " + str(e)[:100]
        self._json(200, {"ok": bool(ok), "msg": msg})


if __name__ == "__main__":
    print(f"Asistan sunucusu: http://localhost:{PORT}  (durdurmak için Ctrl+C)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
