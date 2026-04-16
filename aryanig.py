import os
import time
import threading
import urllib.parse
import requests
import json
from flask import Flask, jsonify, render_template_string
from instagrapi import Client

# --------- CONFIG (via env) ----------
SESSION_ID_1 = os.getenv("SESSION_ID_1")
SESSION_ID_2 = os.getenv("SESSION_ID_2")
SESSION_ID_3 = os.getenv("SESSION_ID_3")
SESSION_ID_4 = os.getenv("SESSION_ID_4")
SESSION_ID_5 = os.getenv("SESSION_ID_5")
SESSION_ID_6 = os.getenv("SESSION_ID_6")

ACC1_GROUP_IDS = os.getenv("ACC1_GROUP_IDS", "")
ACC2_GROUP_IDS = os.getenv("ACC2_GROUP_IDS", "")
ACC3_GROUP_IDS = os.getenv("ACC3_GROUP_IDS", "")
ACC4_GROUP_IDS = os.getenv("ACC4_GROUP_IDS", "")
ACC5_GROUP_IDS = os.getenv("ACC5_GROUP_IDS", "")
ACC6_GROUP_IDS = os.getenv("ACC6_GROUP_IDS", "")

MESSAGE_TEXT = os.getenv("MESSAGE_TEXT", "Hello 👋")
SELF_URL = os.getenv("SELF_URL", "")
NC_TITLES_RAW = os.getenv("NC_TITLES", "")

SPAM_START_OFFSET = int(os.getenv("SPAM_START_OFFSET", "1"))
SPAM_GAP_BETWEEN_ACCOUNTS = int(os.getenv("SPAM_GAP_BETWEEN_ACCOUNTS", "6"))
NC_START_OFFSET = int(os.getenv("NC_START_OFFSET", "1"))
NC_ACC_GAP = int(os.getenv("NC_ACC_GAP", "30"))

MSG_REFRESH_DELAY = int(os.getenv("MSG_REFRESH_DELAY", "1"))
BURST_COUNT = int(os.getenv("BURST_COUNT", "1"))
SELF_PING_INTERVAL = int(os.getenv("SELF_PING_INTERVAL", "60"))
COOLDOWN_ON_ERROR = int(os.getenv("COOLDOWN_ON_ERROR", "300"))

DOC_ID = os.getenv("DOC_ID", "29088580780787855")
CSRF_TOKEN = os.getenv("CSRF_TOKEN", "")

app = Flask(__name__)
MAX_SESSION_LOGS = 200

session_logs = {
    "acc1": [],
    "acc2": [],
    "acc3": [],
    "acc4": [],
    "acc5": [],
    "acc6": [],
    "system": []
}

runtime_state = {
    "started_at": time.time(),
    "accounts": {}
}

logs_lock = threading.Lock()
state_lock = threading.Lock()


def _push_log(session, msg):
    if session not in session_logs:
        session = "system"
    with logs_lock:
        session_logs[session].append(msg)
        if len(session_logs[session]) > MAX_SESSION_LOGS:
            session_logs[session].pop(0)


def log(msg, session="system"):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    _push_log(session, msg)


def set_account_state(acc_name, **kwargs):
    with state_lock:
        if acc_name not in runtime_state["accounts"]:
            runtime_state["accounts"][acc_name] = {}
        runtime_state["accounts"][acc_name].update(kwargs)


def get_account_state(acc_name):
    with state_lock:
        return dict(runtime_state["accounts"].get(acc_name, {}))


def summarize(lines):
    rev = list(reversed(lines))
    last_login = next((l for l in rev if "Logged in" in l), None)
    last_send_ok = next((l for l in rev if "✅" in l and "sent to" in l), None)
    last_send_err = next((l for l in rev if "Send failed" in l or "⚠" in l), None)
    last_title_ok = next((l for l in rev if "changed title" in l and "📝" in l), None)
    last_title_err = next((l for l in rev if "Title change" in l or "GraphQL title" in l), None)
    return {
        "last_login": last_login,
        "last_send_ok": last_send_ok,
        "last_send_error": last_send_err,
        "last_title_ok": last_title_ok,
        "last_title_error": last_title_err,
    }


@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "Bot process alive"})


@app.route("/status")
def status():
    with logs_lock:
        payload = {
            "ok": True,
            "uptime_seconds": int(time.time() - runtime_state["started_at"]),
            "system_last": session_logs["system"][-15:],
            "accounts": {}
        }

        for acc in ["acc1", "acc2", "acc3", "acc4", "acc5", "acc6"]:
            logs = session_logs[acc][-80:]
            payload["accounts"][acc] = {
                "summary": summarize(logs),
                "logs": logs[-20:],
                "state": get_account_state(acc)
            }

    return jsonify(payload)


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Instagram Bot Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {
      --bg: #0b1020;
      --panel: #121936;
      --panel-2: #182247;
      --text: #e8ecff;
      --muted: #a8b1d1;
      --line: #2a3769;
      --green: #2ecc71;
      --red: #ff5d73;
      --yellow: #ffcc66;
      --blue: #61dafb;
      --purple: #8b7bff;
      --chip: #202c5c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, Arial, sans-serif;
      background: linear-gradient(180deg, #0a0f1d, #0f1630);
      color: var(--text);
    }
    .wrap {
      max-width: 1400px;
      margin: 0 auto;
      padding: 20px;
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    .title {
      font-size: 28px;
      font-weight: 700;
    }
    .sub {
      color: var(--muted);
      font-size: 14px;
      margin-top: 4px;
    }
    .btn {
      background: var(--purple);
      color: white;
      border: none;
      border-radius: 10px;
      padding: 10px 14px;
      cursor: pointer;
      font-weight: 600;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }
    .card {
      background: rgba(18, 25, 54, 0.95);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.25);
    }
    .card h3 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    .row {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      margin: 8px 0;
      align-items: center;
    }
    .label { color: var(--muted); font-size: 13px; }
    .value { font-size: 13px; text-align: right; word-break: break-word; }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .chip {
      background: var(--chip);
      border: 1px solid var(--line);
      color: #dbe4ff;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-weight: 700;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
    }
    .ok { background: var(--green); }
    .bad { background: var(--red); }
    .warn { background: var(--yellow); }
    .logs {
      margin-top: 12px;
      max-height: 220px;
      overflow: auto;
      background: #0c1228;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px;
      font-family: Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
    }
    .system {
      margin-top: 20px;
    }
    .system .logs {
      max-height: 300px;
    }
    .mini {
      display: grid;
      grid-template-columns: repeat(4, minmax(0,1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .metric {
      background: rgba(24, 34, 71, 0.95);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
    }
    .metric .k {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .metric .v {
      font-size: 24px;
      font-weight: 700;
    }
    @media (max-width: 1100px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .mini { grid-template-columns: repeat(2, minmax(0,1fr)); }
    }
    @media (max-width: 700px) {
      .grid, .mini { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Instagram Bot Dashboard</div>
        <div class="sub">Live account status, group mapping, logs, health, and runtime overview</div>
      </div>
      <button class="btn" onclick="loadStatus()">Refresh now</button>
    </div>

    <div class="mini" id="metrics"></div>
    <div class="grid" id="cards"></div>

    <div class="system card">
      <h3>System Logs</h3>
      <div class="logs" id="systemLogs">Loading...</div>
    </div>
  </div>

  <script>
    function esc(v) {
      if (v === null || v === undefined) return "-";
      return String(v)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function fmtSeconds(sec) {
      sec = Number(sec || 0);
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = sec % 60;
      return `${h}h ${m}m ${s}s`;
    }

    function boolStatus(active, client_ok) {
      if (active && client_ok) return '<span class="status"><span class="dot ok"></span>Active</span>';
      if (!active && !client_ok) return '<span class="status"><span class="dot bad"></span>Inactive</span>';
      return '<span class="status"><span class="dot warn"></span>Partial</span>';
    }

    async function loadStatus() {
      const res = await fetch('/status');
      const data = await res.json();

      const accounts = data.accounts || {};
      const keys = Object.keys(accounts);

      let activeCount = 0;
      let totalGroups = 0;
      let totalCooldown = 0;

      keys.forEach(k => {
        const st = accounts[k].state || {};
        if (st.active && st.client_ok) activeCount++;
        totalGroups += (st.groups || []).length;
        if (st.cooldown_until && st.cooldown_until > Math.floor(Date.now() / 1000)) totalCooldown++;
      });

      document.getElementById('metrics').innerHTML = `
        <div class="metric"><div class="k">Uptime</div><div class="v">${esc(fmtSeconds(data.uptime_seconds))}</div></div>
        <div class="metric"><div class="k">Accounts Active</div><div class="v">${esc(activeCount)} / 6</div></div>
        <div class="metric"><div class="k">Mapped Groups</div><div class="v">${esc(totalGroups)}</div></div>
        <div class="metric"><div class="k">Cooldown Accounts</div><div class="v">${esc(totalCooldown)}</div></div>
      `;

      let html = '';
      for (const accName of ["acc1","acc2","acc3","acc4","acc5","acc6"]) {
        const item = accounts[accName] || {};
        const st = item.state || {};
        const sm = item.summary || {};
        const logs = item.logs || [];

        const groups = Array.isArray(st.groups) ? st.groups : [];
        const cooldownText = st.cooldown_until_readable || "-";

        html += `
          <div class="card">
            <h3>${esc(accName.toUpperCase())}</h3>

            <div class="row">
              <div class="label">Status</div>
              <div class="value">${boolStatus(!!st.active, !!st.client_ok)}</div>
            </div>

            <div class="row">
              <div class="label">Username</div>
              <div class="value">${esc(st.username || "-")}</div>
            </div>

            <div class="row">
              <div class="label">Cooldown until</div>
              <div class="value">${esc(cooldownText)}</div>
            </div>

            <div class="row">
              <div class="label">Last sent group</div>
              <div class="value">${esc(st.last_sent_gid || "-")}</div>
            </div>

            <div class="row">
              <div class="label">Last title group</div>
              <div class="value">${esc(st.last_title_gid || "-")}</div>
            </div>

            <div class="row">
              <div class="label">Last login</div>
              <div class="value">${esc(sm.last_login || "-")}</div>
            </div>

            <div class="row">
              <div class="label">Last send ok</div>
              <div class="value">${esc(sm.last_send_ok || "-")}</div>
            </div>

            <div class="row">
              <div class="label">Last send error</div>
              <div class="value">${esc(sm.last_send_error || "-")}</div>
            </div>

            <div class="row">
              <div class="label">Last title ok</div>
              <div class="value">${esc(sm.last_title_ok || "-")}</div>
            </div>

            <div class="row">
              <div class="label">Last title error</div>
              <div class="value">${esc(sm.last_title_error || "-")}</div>
            </div>

            <div class="label" style="margin-top:10px;">Mapped groups</div>
            <div class="chips">
              ${groups.length ? groups.map(g => `<span class="chip">${esc(g)}</span>`).join('') : '<span class="chip">No groups</span>'}
            </div>

            <div class="logs">${logs.length ? logs.map(esc).join('<br>') : 'No logs yet'}</div>
          </div>
        `;
      }

      document.getElementById('cards').innerHTML = html;

      const sys = data.system_last || [];
      document.getElementById('systemLogs').innerHTML = sys.length ? sys.map(esc).join('<br>') : 'No system logs yet';
    }

    loadStatus();
    setInterval(loadStatus, 5000);
  </script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


# --------- Utility helpers ----------

def decode_session(session):
    if not session:
        return session
    try:
        return urllib.parse.unquote(session)
    except Exception:
        return session


def parse_groups(raw):
    return [g.strip() for g in raw.split(",") if g.strip()]


# --------- Instagram helpers ----------

def login_session(session_id, name_hint=""):
    session_id = decode_session(session_id)
    try:
        cl = Client()
        cl.login_by_sessionid(session_id)
        uname = getattr(cl, "username", None) or name_hint or "unknown"
        log(f"✅ Logged in {uname}", session=name_hint or "system")
        set_account_state(
            name_hint,
            username=uname,
            active=True,
            client_ok=True
        )
        return cl
    except Exception as e:
        log(f"❌ Login failed ({name_hint}): {e}", session=name_hint or "system")
        set_account_state(
            name_hint,
            username=None,
            active=False,
            client_ok=False
        )
        return None


def safe_send_message(cl, gid, msg, acc_name):
    try:
        cl.direct_send(msg, thread_ids=[int(gid)])
        log(f"✅ {getattr(cl,'username','?')} sent to {gid}", session=acc_name)
        set_account_state(acc_name, last_sent_gid=str(gid), last_action="send")
        return True
    except Exception as e:
        log(f"⚠ Send failed ({getattr(cl,'username','?')}) -> {gid}: {e}", session=acc_name)
        return False


def safe_change_title_direct(cl, gid, new_title, acc_name):
    try:
        tt = cl.direct_thread(int(gid))
        try:
            tt.update_title(new_title)
            log(
                f"📝 {getattr(cl,'username','?')} changed title (direct) for {gid} -> {new_title}",
                session=acc_name
            )
            set_account_state(acc_name, last_title_gid=str(gid), last_action="title_change")
            return True
        except Exception:
            log(
                f"⚠ direct .update_title() failed for {gid} — will attempt GraphQL fallback",
                session=acc_name
            )
    except Exception:
        pass

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "X-CSRFToken": CSRF_TOKEN,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.instagram.com/direct/t/{gid}/",
        }
        cookies = {"csrftoken": CSRF_TOKEN}
        try:
            cl.private.headers.update(headers)
            cl.private.cookies.update(cookies)
            variables = {"thread_fbid": gid, "new_title": new_title}
            payload = {"doc_id": DOC_ID, "variables": json.dumps(variables)}
            resp = cl.private.post("https://www.instagram.com/api/graphql/", data=payload, timeout=10)
            try:
                result = resp.json()
                if "errors" in result:
                    log(f"❌ GraphQL title change errors for {gid}: {result['errors']}", session=acc_name)
                    return False
                log(
                    f"📝 {getattr(cl,'username','?')} changed title (graphql) for {gid} -> {new_title}",
                    session=acc_name
                )
                set_account_state(acc_name, last_title_gid=str(gid), last_action="title_change")
                return True
            except Exception as e:
                log(f"⚠ Title change unexpected response for {gid}: {e} (status {resp.status_code})", session=acc_name)
                return False
        except Exception as e:
            log(f"⚠ Exception performing GraphQL title change for {gid}: {e}", session=acc_name)
            return False
    except Exception as e:
        log(f"⚠ Unexpected fallback error for title change {gid}: {e}", session=acc_name)
        return False


# --------- Loops ----------

def parse_nc_titles():
    base = [t.strip() for t in NC_TITLES_RAW.split(",") if t.strip()]
    default_title = MESSAGE_TEXT[:40] or "NC"
    while len(base) < 6:
        base.append(default_title)
    return base[:6]


def spam_loop(accounts):
    time.sleep(SPAM_START_OFFSET)
    idx = 0
    n = len(accounts)

    while True:
        acc = accounts[idx]
        acc_name = acc["name"]
        acc_groups = acc.get("groups", [])

        try:
            if not acc_groups:
                log(f"ℹ {acc_name} has no groups configured, skipping", session=acc_name)
            elif acc.get("cooldown_until", 0) > time.time():
                log(f"⏳ {acc_name} cooling down", session=acc_name)
            elif not acc["active"] or not acc["client"]:
                log(f"⏭ {acc_name} inactive, skipping message slot", session=acc_name)
            else:
                cl = acc["client"]
                for gid in acc_groups:
                    for _ in range(BURST_COUNT):
                        ok = safe_send_message(cl, gid, MESSAGE_TEXT, acc_name)
                        if not ok:
                            log(f"⛔ {acc_name} failed, applying cooldown for message loop", session=acc_name)
                            acc["cooldown_until"] = time.time() + COOLDOWN_ON_ERROR
                            set_account_state(
                                acc_name,
                                cooldown_until=acc["cooldown_until"],
                                cooldown_until_readable=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(acc["cooldown_until"]))
                            )
                            break
                        time.sleep(MSG_REFRESH_DELAY)

                    if acc.get("cooldown_until", 0) > time.time():
                        break

                    time.sleep(0.5)

        except Exception as e:
            log(f"❌ Exception in {acc_name} message loop: {e}", session=acc_name)
            acc["cooldown_until"] = time.time() + COOLDOWN_ON_ERROR
            set_account_state(
                acc_name,
                cooldown_until=acc["cooldown_until"],
                cooldown_until_readable=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(acc["cooldown_until"]))
            )

        time.sleep(SPAM_GAP_BETWEEN_ACCOUNTS)
        idx = (idx + 1) % n


def nc_loop(accounts, titles_map):
    per_account_titles = parse_nc_titles()
    log(f"NC titles per account: {per_account_titles}", session="system")

    time.sleep(NC_START_OFFSET)
    idx = 0
    n = len(accounts)

    while True:
        acc = accounts[idx]
        acc_name = acc["name"]
        acc_groups = acc.get("groups", [])
        account_title = per_account_titles[idx]

        try:
            if not acc_groups:
                log(f"ℹ {acc_name} has no groups configured for title change, skipping", session=acc_name)
            elif acc.get("cooldown_until", 0) > time.time():
                log(f"⏳ {acc_name} cooling down", session=acc_name)
            elif not acc["active"] or not acc["client"]:
                log(f"⏭ {acc_name} inactive, skipping nc slot", session=acc_name)
            else:
                cl = acc["client"]
                for gid in acc_groups:
                    titles = titles_map.get(str(gid)) or titles_map.get(int(gid)) or [account_title]
                    t = titles[0]

                    ok = safe_change_title_direct(cl, gid, t, acc_name)
                    if not ok:
                        log(f"⛔ {acc_name} failed, applying cooldown for nc loop", session=acc_name)
                        acc["cooldown_until"] = time.time() + COOLDOWN_ON_ERROR
                        set_account_state(
                            acc_name,
                            cooldown_until=acc["cooldown_until"],
                            cooldown_until_readable=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(acc["cooldown_until"]))
                        )
                        break

                    time.sleep(1)

        except Exception as e:
            log(f"❌ Exception in {acc_name} nc loop: {e}", session=acc_name)
            acc["cooldown_until"] = time.time() + COOLDOWN_ON_ERROR
            set_account_state(
                acc_name,
                cooldown_until=acc["cooldown_until"],
                cooldown_until_readable=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(acc["cooldown_until"]))
            )

        time.sleep(NC_ACC_GAP)
        idx = (idx + 1) % n


def self_ping_loop():
    while True:
        if SELF_URL:
            try:
                requests.get(SELF_URL, timeout=10)
                log("🔁 Self ping successful", session="system")
            except Exception as e:
                log(f"⚠ Self ping failed: {e}", session="system")
        time.sleep(SELF_PING_INTERVAL)


def start_bot():
    sessions = [
        decode_session(SESSION_ID_1),
        decode_session(SESSION_ID_2),
        decode_session(SESSION_ID_3),
        decode_session(SESSION_ID_4),
        decode_session(SESSION_ID_5),
        decode_session(SESSION_ID_6),
    ]

    acc_group_map = {
        1: parse_groups(ACC1_GROUP_IDS),
        2: parse_groups(ACC2_GROUP_IDS),
        3: parse_groups(ACC3_GROUP_IDS),
        4: parse_groups(ACC4_GROUP_IDS),
        5: parse_groups(ACC5_GROUP_IDS),
        6: parse_groups(ACC6_GROUP_IDS),
    }

    titles_map = {}
    raw_titles = os.getenv("GROUP_TITLES", "")
    if raw_titles:
        try:
            titles_map = json.loads(raw_titles)
        except Exception as e:
            log(f"⚠ GROUP_TITLES JSON parse error: {e}. Using fallback titles.", session="system")

    accounts = []

    for i, s in enumerate(sessions, 1):
        acc_name = f"acc{i}"
        groups = acc_group_map.get(i, [])

        set_account_state(
            acc_name,
            groups=groups,
            active=False,
            client_ok=False,
            username=None,
            cooldown_until=0,
            cooldown_until_readable="-",
            last_sent_gid="-",
            last_title_gid="-"
        )

        if not s:
            log(f"⚠ No session for {acc_name}, keeping slot inactive", session=acc_name)
            accounts.append({
                "name": acc_name,
                "client": None,
                "active": False,
                "cooldown_until": 0,
                "groups": groups
            })
            continue

        log(f"🔐 Logging in account {i}...", session="system")
        cl = login_session(s, acc_name)
        if cl:
            uname = getattr(cl, "username", None) or acc_name
            set_account_state(acc_name, username=uname, active=True, client_ok=True, groups=groups)
            accounts.append({
                "name": acc_name,
                "client": cl,
                "active": True,
                "cooldown_until": 0,
                "groups": groups
            })
        else:
            log(f"⚠ {acc_name} login failed, keeping slot inactive", session=acc_name)
            accounts.append({
                "name": acc_name,
                "client": None,
                "active": False,
                "cooldown_until": 0,
                "groups": groups
            })

    if not any(a["client"] for a in accounts):
        log("❌ No accounts logged in, aborting.", session="system")
        return

    try:
        t1 = threading.Thread(target=spam_loop, args=(accounts,), daemon=True)
        t1.start()
        log("▶ Started spam loop", session="system")
    except Exception as e:
        log(f"❌ Failed to start spam loop thread: {e}", session="system")

    try:
        t2 = threading.Thread(target=nc_loop, args=(accounts, titles_map), daemon=True)
        t2.start()
        log("▶ Started nc loop", session="system")
    except Exception as e:
        log(f"❌ Failed to start nc loop thread: {e}", session="system")

    try:
        t3 = threading.Thread(target=self_ping_loop, daemon=True)
        t3.start()
        log("▶ Started self-ping loop", session="system")
    except Exception as e:
        log(f"⚠ Failed to start self-ping thread: {e}", session="system")


def run_bot_once():
    try:
        threading.Thread(target=start_bot, daemon=True).start()
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ Failed to start bot (import-time): {e}", flush=True)


run_bot_once()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    log(f"HTTP server starting on port {port}", session="system")
    try:
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        log(f"❌ Flask run failed: {e}", session="system")
