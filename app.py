# app.py
# 依存: pip install customtkinter playwright
# 初回: playwright install chromium

import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import logging
import threading
import traceback
import socket
import ssl
import random
import ipaddress
from pathlib import Path
from urllib.parse import urlparse

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog


# ---------------- ログ ----------------

def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def _setup_file_logging():
    try:
        log_dir = Path(get_app_dir())
    except Exception:
        log_dir = Path.cwd()
    logging.basicConfig(
        filename=str(log_dir / "app.log"),
        level=logging.DEBUG,
        format="%(asctime)s [%(threadName)s] %(levelname)s: %(message)s",
        encoding="utf-8",
        force=True,
    )


_setup_file_logging()


# ---------------- 定数 ----------------

MESSENGER_POOL = [
    "www.gov.tw",
    "www.104.com.tw",
    "www.1111.com.tw",
    "www.pchome.com.tw",
]
DEFAULT_TARGET = "www.aiixi.cc"

COLO_INFO = {
    "HKG": "香港", "NRT": "東京", "HND": "東京", "KIX": "大阪",
    "TPE": "台北", "TSA": "台北", "SIN": "シンガポール",
    "ICN": "ソウル", "BKK": "バンコク", "KUL": "クアラルンプール",
    "MNL": "マニラ", "SGN": "ホーチミン", "CGK": "ジャカルタ",
    "LAX": "ロサンゼルス", "SJC": "サンノゼ", "SFO": "サンフランシスコ",
    "SEA": "シアトル", "DFW": "ダラス", "ORD": "シカゴ",
    "IAD": "ワシントン", "JFK": "ニューヨーク", "EWR": "ニューヨーク",
    "YYZ": "トロント", "LHR": "ロンドン", "FRA": "フランクフルト",
    "AMS": "アムステルダム", "CDG": "パリ", "MAD": "マドリード",
    "SYD": "シドニー", "MEL": "メルボルン", "AKL": "オークランド",
    "BOM": "ムンバイ", "DEL": "デリー", "DXB": "ドバイ",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ---------------- ネットワーク ----------------

def resolve_ip(domain, prefer_ipv6=True, timeout=5):
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        infos = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
    finally:
        socket.setdefaulttimeout(old)
    v6, v4 = [], []
    for info in infos:
        addr = info[4][0]
        if ":" in addr:
            if addr not in v6:
                v6.append(addr)
        else:
            if addr not in v4:
                v4.append(addr)
    if prefer_ipv6 and v6:
        return random.choice(v6)
    if v4:
        return random.choice(v4)
    if v6:
        return random.choice(v6)
    raise RuntimeError(f"{domain} の IP を解決できません")


def pick_messenger_ip(pool, prefer_ipv6=True, log=print):
    shuffled = pool[:]
    random.shuffle(shuffled)
    errors = []
    for domain in shuffled:
        try:
            ip = resolve_ip(domain, prefer_ipv6=prefer_ipv6)
            log(f"[メッセンジャー] {domain} -> {ip}")
            return domain, ip
        except Exception as e:
            errors.append(f"{domain}: {e}")
            log(f"[メッセンジャー] {domain} の解析に失敗: {e}")
    raise RuntimeError(
        "すべてのメッセンジャードメインの解析に失敗:\n" + "\n".join(errors)
    )


def normalize_ip_for_rule(ip):
    ip = ip.strip().strip("[]")
    ipaddress.ip_address(ip)
    return f"[{ip}]" if ":" in ip else ip


def fetch_cf_trace(hostname, ip, timeout=10):
    ip_clean = ip.strip().strip("[]")
    ctx = ssl.create_default_context()
    sock = socket.create_connection((ip_clean, 443), timeout=timeout)
    try:
        ssock = ctx.wrap_socket(sock, server_hostname=hostname)
    except Exception:
        sock.close()
        raise
    try:
        req = (
            f"GET /cdn-cgi/trace HTTP/1.1\r\n"
            f"Host: {hostname}\r\n"
            f"User-Agent: dns-bypass-tool\r\n"
            f"Connection: close\r\n\r\n"
        )
        ssock.sendall(req.encode("ascii"))
        data = b""
        while True:
            chunk = ssock.recv(4096)
            if not chunk:
                break
            data += chunk
    finally:
        try:
            ssock.close()
        except Exception:
            pass

    text = data.decode("utf-8", errors="replace")
    _, body = text.split("\r\n\r\n", 1) if "\r\n\r\n" in text else ("", text)
    result = {}
    for line in body.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    if not result:
        raise RuntimeError(f"/cdn-cgi/trace の応答が不正: {body[:100]!r}")
    return result


def format_trace(result, expect_host=None):
    colo = result.get("colo", "?")
    city = COLO_INFO.get(colo, "")
    loc = result.get("loc", "")
    h = result.get("h", "")
    node_str = f"{colo} ({city})" if city else colo
    parts = [f"ノード: {node_str}"]
    if loc:
        parts.append(f"loc={loc}")
    if expect_host and h:
        parts.append("host✓" if h == expect_host else f"host✗(h={h})")
    return ", ".join(parts)


# ---------------- ブラウザパス ----------------

def validate_browsers_path(path_str):
    if not path_str or not str(path_str).strip():
        return False, "パスが空です"
    p = Path(str(path_str).strip().strip('"'))
    if not p.exists():
        return False, f"パスが存在しません: {p}"
    if not p.is_dir():
        return False, f"フォルダではありません: {p}"
    try:
        has_chromium = any(
            d.is_dir() and d.name.startswith("chromium-")
            for d in p.iterdir()
        )
    except PermissionError:
        return False, f"アクセス拒否: {p}"
    if not has_chromium:
        return False, f"chromium-* フォルダが見つかりません: {p}"
    return True, str(p.resolve())


def auto_detect_browsers_path():
    base = get_app_dir()
    for name in ("playwright-browsers", "browser", "browsers", "ms-playwright"):
        ok, msg = validate_browsers_path(os.path.join(base, name))
        if ok:
            return msg
    try:
        for entry in sorted(os.listdir(base)):
            full = os.path.join(base, entry)
            if not os.path.isdir(full):
                continue
            if entry.startswith(("playwright-browsers", "chromium")):
                ok, msg = validate_browsers_path(full)
                if ok:
                    return msg
    except Exception:
        pass
    return ""


# ---------------- マッピング規則 ----------------

def build_host_resolver_rule(hostname, ip, extra_mappings=None):
    ip_rule = normalize_ip_for_rule(ip)
    rules = [f"MAP {hostname} {ip_rule}"]

    parts = hostname.split(".")
    if len(parts) == 2:
        rules.append(f"MAP *.{hostname} {ip_rule}")
    elif len(parts) >= 3:
        base = ".".join(parts[-2:])
        if base != hostname:
            rules.append(f"MAP {base} {ip_rule}")
        rules.append(f"MAP *.{base} {ip_rule}")

    if extra_mappings:
        for h, extra_ip in extra_mappings:
            h = (h or "").strip()
            if not h:
                continue
            try:
                use_ip = normalize_ip_for_rule(extra_ip) if extra_ip else ip_rule
            except Exception:
                continue
            rules.append(f"MAP {h} {use_ip}")
            if not h.startswith("*.") and h.count(".") == 1:
                rules.append(f"MAP *.{h} {use_ip}")

    seen = set()
    deduped = []
    for r in rules:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return ", ".join(deduped)


def parse_extra_mappings(text):
    result = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        host = parts[0].strip()
        ip = parts[1].strip() if len(parts) >= 2 else None
        if host:
            result.append((host, ip))
    return result


# ---------------- ブラウザ起動 ----------------

def launch_browser(url, hostname, ip, browsers_path, headless, log=print,
                   extra_mappings=None):
    if browsers_path:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
        log(f"[ブラウザパス] PLAYWRIGHT_BROWSERS_PATH = {browsers_path}")
    else:
        existing = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        if existing:
            log(f"[ブラウザパス] 既存の環境変数を使用: {existing}")
        else:
            log("[ブラウザパス] 未指定 → Playwright デフォルトのキャッシュを使用")

    from playwright.sync_api import sync_playwright

    rule = build_host_resolver_rule(hostname, ip, extra_mappings)
    log(f"[ルール] --host-resolver-rules={rule}")
    args = [f"--host-resolver-rules={rule}", "--lang=ja", "--accept-lang=ja,en;q=0.8"]

    with sync_playwright() as p:
        log(f"[実行ファイル] {p.chromium.executable_path}")
        browser = p.chromium.launch(headless=headless, args=args)
        page = browser.new_context().new_page()
        page.on("pageerror", lambda e: log(f"[ページエラー] {e}"))

        failed_domains = set()

        def on_request_failed(req):
            failure = req.failure or "unknown"
            u = req.url
            try:
                host = (urlparse(u).hostname or "")
            except Exception:
                host = ""
            log(f"[リクエスト失敗] {failure} - {u}")
            if host:
                failed_domains.add(host)

        page.on("requestfailed", on_request_failed)

        log(f"[開く] {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            log(f"[完了] 現在のアドレス: {page.url}")
        except Exception as e:
            log(f"[開くのに失敗] {e}")

        def report_failed():
            if failed_domains:
                log("[注意] 以下のドメインでリクエストが失敗しました。"
                    "必要なら「追加マッピング」に追加してください：")
                for d in sorted(failed_domains):
                    log(f"  - {d}")

        if headless:
            try:
                page.wait_for_timeout(3000)
            except Exception:
                pass
            log(f"[HTML 長さ] {len(page.content())}")
            browser.close()
            report_failed()
        else:
            log("[ヒント] ブラウザを開きました。ウィンドウを閉じると終了します")
            closed = threading.Event()
            browser.on("disconnected", lambda _: closed.set())
            closed.wait()
            log("[終了] ブラウザが閉じられました")
            report_failed()


# ---------------- GUI ----------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("愛希の Cloudflare SNI マッピングツール")
        # 初期サイズは控えめに、最小サイズも小さめにして、スクロールで全部見られるように
        self.geometry("820x700")
        self.minsize(720, 420)

        if sys.platform == "win32":
            family = "Yu Gothic UI"
        elif sys.platform == "darwin":
            family = "Hiragino Sans"
        else:
            family = "Noto Sans CJK JP"

        self.font_title = ctk.CTkFont(family=family, size=20, weight="bold")
        self.font_body  = ctk.CTkFont(family=family, size=13)
        self.font_label = ctk.CTkFont(family=family, size=12, weight="bold")
        self.font_log   = ctk.CTkFont(
            family="Consolas" if sys.platform == "win32" else "Menlo", size=12
        )
        self.font_hint  = ctk.CTkFont(family=family, size=11)

        # ===== 全コンテンツを包むスクロールコンテナ =====
        self.main_scroll = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.main_scroll.pack(fill="both", expand=True, padx=0, pady=0)
        self.main_scroll.grid_columnconfigure(0, weight=1)

        # ===== ヘッダー =====
        header = ctk.CTkFrame(self.main_scroll, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text="🌐  愛希の Cloudflare SNI マッピングツール（大便版）",
            font=self.font_title, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.theme_switch = ctk.CTkSwitch(
            header, text="ライトモード", command=self.toggle_theme,
            font=self.font_body,
        )
        self.theme_switch.grid(row=0, column=1, sticky="e")

        # ===== 設定カード =====
        cfg = ctk.CTkFrame(self.main_scroll, corner_radius=14)
        cfg.grid(row=1, column=0, sticky="ew", padx=20, pady=8)
        cfg.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(cfg, text="設定", font=self.font_label, anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(14, 6)
        )

        ctk.CTkLabel(cfg, text="ターゲットドメイン", font=self.font_body, anchor="w").grid(
            row=1, column=0, sticky="w", padx=(18, 10), pady=6
        )
        self.target_var = tk.StringVar(value=DEFAULT_TARGET)
        ctk.CTkEntry(cfg, textvariable=self.target_var, height=36, font=self.font_body).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(0, 18), pady=6
        )

        ctk.CTkLabel(cfg, text="ターゲット URL", font=self.font_body, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(18, 10), pady=6
        )
        self.url_var = tk.StringVar()
        ctk.CTkEntry(
            cfg, textvariable=self.url_var, height=36, font=self.font_body,
            placeholder_text=f"空欄時は https://{DEFAULT_TARGET}/ を使用",
        ).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 18), pady=6)

        ctk.CTkLabel(cfg, text="メッセンジャードメイン", font=self.font_body, anchor="w").grid(
            row=3, column=0, sticky="w", padx=(18, 10), pady=6
        )
        self.messenger_var = tk.StringVar(value=MESSENGER_POOL[0])
        ctk.CTkEntry(cfg, textvariable=self.messenger_var, height=36, font=self.font_body).grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=(0, 18), pady=6
        )

        ctk.CTkLabel(cfg, text="ターゲット IP", font=self.font_body, anchor="w").grid(
            row=4, column=0, sticky="w", padx=(18, 10), pady=6
        )
        self.ip_var = tk.StringVar()
        ctk.CTkEntry(cfg, textvariable=self.ip_var, height=36, font=self.font_body).grid(
            row=4, column=1, sticky="ew", padx=(0, 8), pady=6
        )
        ctk.CTkButton(
            cfg, text="自動取得", width=100, height=36,
            font=self.font_body, command=self.on_auto_ip,
        ).grid(row=4, column=2, sticky="e", padx=(0, 18), pady=6)

        ctk.CTkLabel(cfg, text="ブラウザパス", font=self.font_body, anchor="w").grid(
            row=5, column=0, sticky="w", padx=(18, 10), pady=6
        )
        self.browsers_var = tk.StringVar()
        ctk.CTkEntry(
            cfg, textvariable=self.browsers_var, height=36, font=self.font_body,
            placeholder_text="空欄時は Playwright デフォルトを使用",
        ).grid(row=5, column=1, sticky="ew", padx=(0, 8), pady=6)
        ctk.CTkButton(
            cfg, text="参照…", width=100, height=36,
            font=self.font_body, command=self.on_pick_browsers_dir,
        ).grid(row=5, column=2, sticky="e", padx=(0, 18), pady=6)
        ctk.CTkLabel(
            cfg,
            text="※ chromium-* フォルダを含む親フォルダを指定（例: .\\playwright-browsers）",
            font=self.font_hint, text_color=("gray40", "gray65"), anchor="w",
        ).grid(row=6, column=1, columnspan=2, sticky="w", padx=(0, 18), pady=(0, 6))

        ctk.CTkLabel(cfg, text="追加マッピング", font=self.font_body, anchor="nw").grid(
            row=7, column=0, sticky="nw", padx=(18, 10), pady=6
        )
        self.extra_mappings_box = ctk.CTkTextbox(
            cfg, height=80, font=self.font_body, corner_radius=8, wrap="none",
        )
        self.extra_mappings_box.grid(
            row=7, column=1, columnspan=2, sticky="ew", padx=(0, 18), pady=6
        )
        self.extra_mappings_box.insert(
            "1.0",
            "# 一行に 1 ドメイン。IP を省略すると主 IP を使用\n"
            "# 例: api.partner.com\n"
            "# 例: cdn.example.net 203.0.113.42\n"
        )
        ctk.CTkLabel(
            cfg,
            text="※ 同一ベースドメインのサブドメイン（*.example.com）は自動でカバーされます。"
                 "外部ドメインのみここに追加。",
            font=self.font_hint, text_color=("gray40", "gray65"), anchor="w",
        ).grid(row=8, column=1, columnspan=2, sticky="w", padx=(0, 18), pady=(0, 6))

        node_row = ctk.CTkFrame(cfg, fg_color="transparent")
        node_row.grid(row=9, column=0, columnspan=3, sticky="ew", padx=18, pady=(4, 6))
        ctk.CTkLabel(
            node_row, text="現在のノード：", font=self.font_body,
            text_color=("gray40", "gray65"),
        ).pack(side="left")
        self.node_label = ctk.CTkLabel(
            node_row, text="未取得", font=self.font_body,
            text_color=("#2980b9", "#66aaff"), anchor="w",
        )
        self.node_label.pack(side="left", padx=(4, 0))

        self.headless_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            cfg, text="ヘッドレスモード（ブラウザ UI 非表示）",
            variable=self.headless_var, font=self.font_body,
        ).grid(row=10, column=0, columnspan=3, sticky="w", padx=18, pady=(4, 14))

        # ===== ボタン列 =====
        btn_row = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 8))
        ctk.CTkButton(
            btn_row, text="🔍  解析テスト", height=44, width=140,
            font=self.font_body, command=self.on_auto_ip,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btn_row, text="🛰  ノード確認", height=44, width=140,
            font=self.font_body, command=self.on_check_node,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btn_row, text="🚀  ブラウザ起動", height=44, width=180,
            font=self.font_body, command=self.on_launch,
        ).pack(side="left")

        # ===== ログカード（スクロール内なので固定高さ） =====
        log_card = ctk.CTkFrame(self.main_scroll, corner_radius=14)
        log_card.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 8))
        log_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_card, text="ログ", font=self.font_label, anchor="w").grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 4)
        )
        self.log_box = ctk.CTkTextbox(
            log_card, font=self.font_log, wrap="word",
            corner_radius=10, border_spacing=8, height=260,
        )
        self.log_box.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))
        self.log_box.configure(state="disabled")

        # ===== ステータスバー =====
        status = ctk.CTkFrame(self.main_scroll, height=32, fg_color="transparent")
        status.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 14))
        self.status_dot = ctk.CTkLabel(
            status, text="●", font=self.font_body, text_color="#8a8a8a"
        )
        self.status_dot.pack(side="left")
        self.status_label = ctk.CTkLabel(
            status, text="待機中", font=self.font_body,
            text_color=("gray40", "gray65"),
        )
        self.status_label.pack(side="left", padx=(6, 0))

        # ===== 起動時の初期化 =====
        detected = auto_detect_browsers_path()
        if detected:
            self.browsers_var.set(detected)
            self.log(f"[ブラウザパス] 自動検出: {detected}")
        else:
            self.log("[ブラウザパス] 自動検出なし（必要なら手動で指定してください）")
        self.log(f"[起動] app dir = {get_app_dir()}")
        self.log("[待機] 設定を入力して「ブラウザ起動」を押してください")

    # ---------- 共通 ----------
    def toggle_theme(self):
        ctk.set_appearance_mode("light" if self.theme_switch.get() else "dark")

    def set_status(self, text, color="#8a8a8a"):
        self.status_dot.configure(text_color=color)
        self.status_label.configure(text=text)

    def log(self, msg):
        line = str(msg)
        print(line, flush=True)
        logging.debug(line)
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def update_node_display(self, result):
        colo = result.get("colo", "?")
        city = COLO_INFO.get(colo, "")
        text = f"{colo} · {city}" if city else colo
        if result.get("loc"):
            text += f"  [{result['loc']}]"
        self.node_label.configure(text=text)

    def clear_node_display(self):
        self.node_label.configure(text="取得失敗")

    # ---------- ブラウザパス選択 ----------
    def on_pick_browsers_dir(self):
        current = self.browsers_var.get().strip().strip('"')
        if current and os.path.isdir(current):
            initial = current
        else:
            initial = get_app_dir()
        if not os.path.isdir(initial):
            initial = os.getcwd()

        d = filedialog.askdirectory(
            title="chromium-* フォルダを含む親フォルダを選択",
            initialdir=initial,
        )
        if d:
            self.browsers_var.set(d)
            ok, msg = validate_browsers_path(d)
            if ok:
                self.log(f"[ブラウザパス] OK: {msg}")
            else:
                self.log(f"[ブラウザパス] 警告: {msg}")

    # ---------- ターゲット解決 ----------
    def _resolve_target(self):
        url = (self.url_var.get() or "").strip()
        domain = (self.target_var.get() or "").strip().lower()
        if not url:
            if not domain:
                raise ValueError("ターゲット URL またはドメインを入力してください")
            return f"https://{domain}/", domain
        if "://" not in url:
            url = "https://" + url
        host = (urlparse(url).hostname or "").lower()
        if not host:
            raise ValueError(f"URL からホスト名を抽出できません: {url}")
        if domain and domain != host:
            self.log(
                f"[警告] URL ホスト ({host}) と ターゲットドメイン ({domain}) が異なります "
                f"→ {host} をキーにします"
            )
        return url, host

    def _resolve_and_trace(self):
        url, host = self._resolve_target()
        messenger = self.messenger_var.get().strip()
        if not messenger:
            domain, ip = pick_messenger_ip(MESSENGER_POOL, log=self.log)
            self.messenger_var.set(domain)
        else:
            ip = resolve_ip(messenger)
            self.log(f"[解析] {messenger} -> {ip}")
        self.ip_var.set(ip)
        normalize_ip_for_rule(ip)
        trace = fetch_cf_trace(host, ip)
        self.log(f"[ノード] {format_trace(trace, expect_host=host)}")
        self.update_node_display(trace)
        return url, host, ip

    def _get_extra_mappings(self):
        raw = self.extra_mappings_box.get("1.0", "end")
        return parse_extra_mappings(raw)

    # ---------- ボタン ----------
    def on_auto_ip(self):
        self.set_status("解析中...", "#f5a623")

        def worker():
            try:
                self._resolve_and_trace()
                self.log("[成功] IP とノードを取得しました")
                self.set_status(f"準備完了: {self.ip_var.get()}", "#2ecc71")
            except Exception as e:
                tb = traceback.format_exc()
                self.log(f"[失敗] {e}")
                self.log(tb)
                self.set_status("失敗", "#e74c3c")
                messagebox.showerror("解析失敗", f"{e}\n\n詳細はログ / app.log を参照")

        threading.Thread(target=worker, daemon=True).start()

    def on_check_node(self):
        ip = self.ip_var.get().strip()
        if not ip:
            messagebox.showwarning("入力エラー", "先に IP を取得してください")
            return
        self.set_status("ノード確認中...", "#f5a623")

        def worker():
            try:
                _, host = self._resolve_target()
                normalize_ip_for_rule(ip)
                trace = fetch_cf_trace(host, ip.strip("[]"))
                self.log(f"[ノード] {format_trace(trace, expect_host=host)}")
                self.update_node_display(trace)
                self.set_status("ノード確認完了", "#2ecc71")
            except Exception as e:
                tb = traceback.format_exc()
                self.log(f"[ノード] 取得失敗: {e}")
                self.log(tb)
                self.clear_node_display()
                self.set_status("失敗", "#e74c3c")
                messagebox.showerror("ノード確認失敗", f"{e}\n\n詳細はログ / app.log を参照")

        threading.Thread(target=worker, daemon=True).start()

    def on_launch(self):
        browsers_path = self.browsers_var.get().strip()
        if browsers_path:
            ok, msg = validate_browsers_path(browsers_path)
            if not ok:
                self.log(f"[ブラウザパス] エラー: {msg}")
                if not messagebox.askyesno(
                    "ブラウザパスの確認",
                    f"指定されたパスに問題があります:\n{msg}\n\nこのまま起動を試みますか？",
                ):
                    return
            else:
                self.log(f"[ブラウザパス] 検証 OK: {msg}")
                browsers_path = msg

        extra = self._get_extra_mappings()
        if extra:
            self.log(f"[追加マッピング] {len(extra)} 件")
            for h, ei in extra:
                self.log(f"  - {h} → {ei or '(主IP)'}")

        self.set_status("起動中...", "#f5a623")
        ip = self.ip_var.get().strip()

        def worker():
            try:
                if not ip:
                    url, host, ip_used = self._resolve_and_trace()
                else:
                    url, host = self._resolve_target()
                    ip_used = ip.strip("[]")
                    normalize_ip_for_rule(ip_used)
                    try:
                        trace = fetch_cf_trace(host, ip_used)
                        self.log(f"[ノード] {format_trace(trace, expect_host=host)}")
                        self.update_node_display(trace)
                    except Exception as e:
                        self.log(f"[ノード] /cdn-cgi/trace 取得失敗: {e}")
                        self.clear_node_display()

                self.set_status("ブラウザ実行中", "#3498db")
                launch_browser(
                    url=url, hostname=host, ip=ip_used,
                    browsers_path=browsers_path,
                    headless=self.headless_var.get(),
                    log=self.log,
                    extra_mappings=extra,
                )
                self.set_status("完了", "#2ecc71")
            except Exception as e:
                tb = traceback.format_exc()
                self.log(f"[エラー] {e}")
                self.log(tb)
                self.set_status("エラー", "#e74c3c")
                messagebox.showerror(
                    "起動失敗",
                    f"{e}\n\n詳細はログ / app.log を参照",
                )

        threading.Thread(target=worker, daemon=True).start()


# ---------------- 起動 ----------------

def _install_thread_excepthook():
    def hook(args):
        msg = "".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback
        ))
        line = f"[未捕獲スレッド例外] {args.thread.name}\n{msg}"
        print(line, file=sys.stderr, flush=True)
        try:
            logging.error(line)
        except Exception:
            pass
    threading.excepthook = hook


if __name__ == "__main__":
    _install_thread_excepthook()
    try:
        App().mainloop()
    except KeyboardInterrupt:
        print("\n[終了] ユーザーにより中断されました", flush=True)
        sys.exit(0)
    except Exception:
        tb = traceback.format_exc()
        print(tb, flush=True)
        try:
            logging.error("mainloop crashed:\n%s", tb)
        except Exception:
            pass
        try:
            messagebox.showerror("致命的エラー", tb)
        except Exception:
            pass
        sys.exit(1)