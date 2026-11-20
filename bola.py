import os
import time
import html
import sqlite3
import base64
from datetime import datetime, date
from flask import Flask, request, redirect, url_for, session, flash, get_flashed_messages, g, make_response

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "yotoqxona-super-admin-2026-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("YOTOQXONA_DB_PATH") or os.path.join(BASE_DIR, "yotoqxona.db")
UPLOAD_DIR = os.environ.get("YOTOQXONA_UPLOAD_DIR") or os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

PINS = {
    "ustoz": os.environ.get("PIN_USTOZ", "1111"),
    "oshpaz": os.environ.get("PIN_OSHPAZ", "2222"),
    "superadmin": os.environ.get("PIN_SUPERADMIN", "9999"),
}

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
failed_logins = {}


def esc(val):
    return html.escape(str(val or ""), quote=True)


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def is_login_locked(ip):
    rec = failed_logins.get(ip)
    if not rec:
        return False, 0
    locked_until = rec.get("locked_until", 0)
    now = time.time()
    if locked_until > now:
        return True, int(locked_until - now) + 1
    if locked_until and locked_until <= now:
        failed_logins.pop(ip, None)
    return False, 0


def record_failed_login(ip):
    now = time.time()
    rec = failed_logins.get(ip, {"count": 0, "locked_until": 0})
    rec["count"] += 1
    if rec["count"] >= MAX_LOGIN_ATTEMPTS:
        rec["locked_until"] = now + LOCKOUT_SECONDS
        rec["count"] = 0
    failed_logins[ip] = rec


def clear_failed_login(ip):
    failed_logins.pop(ip, None)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def today_str():
    return date.today().strftime("%Y-%m-%d")


def format_uz_date(iso_date):
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
    except ValueError:
        dt = datetime.now()
    months = [
        "", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
        "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"
    ]
    weekdays = [
        "Dushanba", "Seshanba", "Chorshanba", "Payshanba",
        "Juma", "Shanba", "Yakshanba"
    ]
    return f"{dt.day}-{months[dt.month]} {dt.year}-yil, {weekdays[dt.weekday()]}"


def auto_theme_by_hour():
    hour = datetime.now().hour
    return "day" if 6 <= hour < 18 else "night"


def detect_device_mode():
    if session.get("device_mode") in ("phone", "desktop"):
        return session["device_mode"]
    ua = (request.headers.get("User-Agent") or "").lower()
    if any(k in ua for k in ("iphone", "android", "mobile", "ipod", "opera mini", "windows phone")):
        return "phone"
    return "desktop"


def init_db():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            sub_label TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            UNIQUE(code, sub_label)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            room_id INTEGER NOT NULL,
            FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            work_date TEXT NOT NULL,
            status TEXT DEFAULT '',
            reason_type TEXT DEFAULT '',
            reason_note TEXT DEFAULT '',
            phone_status TEXT DEFAULT '',
            phone_given INTEGER DEFAULT 0,
            phone_photo TEXT DEFAULT '',
            phone_time TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            UNIQUE(student_id, work_date),
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
        )
    """)

    cols = [r[1] for r in cur.execute("PRAGMA table_info(attendance)").fetchall()]
    if "phone_status" not in cols:
        cur.execute("ALTER TABLE attendance ADD COLUMN phone_status TEXT DEFAULT ''")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS supervisors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_number INTEGER UNIQUE NOT NULL,
            teacher_name TEXT NOT NULL,
            shift_start TEXT NOT NULL,
            shift_end TEXT NOT NULL,
            on_time INTEGER DEFAULT 0,
            arrived_at TEXT DEFAULT ''
        )
    """)

    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_theme', '1')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_seen_date', ?)", (today_str(),))

    cur.execute("SELECT COUNT(*) FROM supervisors")
    if cur.fetchone()[0] == 0:
        default_supervisors = [
            (1, "1-Ustoz", "07:00", "15:00", 0, ""),
            (2, "2-Ustoz", "15:00", "23:00", 0, ""),
            (3, "3-Ustoz", "23:00", "07:00", 0, ""),
        ]
        cur.executemany("""
            INSERT INTO supervisors (slot_number, teacher_name, shift_start, shift_end, on_time, arrived_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, default_supervisors)

    cur.execute("SELECT COUNT(*) FROM rooms")
    if cur.fetchone()[0] == 0:
        for i in range(1, 13):
            code = f"{i}c"
            cur.execute("INSERT OR IGNORE INTO rooms (code, sub_label, capacity) VALUES (?, '6 kishilik xona', 6)", (code,))
            cur.execute("INSERT OR IGNORE INTO rooms (code, sub_label, capacity) VALUES (?, '4 kishilik xona', 4)", (code,))

    cur.execute("SELECT COUNT(*) FROM students")
    if cur.fetchone()[0] == 0:
        r1_6 = cur.execute("SELECT id FROM rooms WHERE code = '1c' AND sub_label = '6 kishilik xona'").fetchone()[0]
        r1_4 = cur.execute("SELECT id FROM rooms WHERE code = '1c' AND sub_label = '4 kishilik xona'").fetchone()[0]
        r2_6 = cur.execute("SELECT id FROM rooms WHERE code = '2c' AND sub_label = '6 kishilik xona'").fetchone()[0]
        r3_4 = cur.execute("SELECT id FROM rooms WHERE code = '3c' AND sub_label = '4 kishilik xona'").fetchone()[0]

        sample_students = [
            ("Ali Valiyev", "7-A sinf", r1_6),
            ("Bekzod Karimov", "7-A sinf", r1_6),
            ("Jasur Tursunov", "8-B sinf", r1_6),
            ("Sardor Alimov", "8-B sinf", r1_4),
            ("Azizbek Sobirov", "9-A sinf", r1_4),
            ("Dostonbek Qodirov", "9-A sinf", r2_6),
            ("Sherzod Xolmatov", "10-A sinf", r2_6),
            ("Javohir Abdullayev", "10-B sinf", r3_4),
        ]
        cur.executemany(
            "INSERT INTO students (full_name, class_name, room_id) VALUES (?, ?, ?)",
            sample_students
        )

    db.commit()
    db.close()


init_db()


def ensure_day_rollover():
    db = get_db()
    cur = db.cursor()
    cur_date = today_str()

    try:
        row = cur.execute("SELECT value FROM settings WHERE key = 'last_seen_date'").fetchone()
    except sqlite3.OperationalError:
        init_db()
        row = cur.execute("SELECT value FROM settings WHERE key = 'last_seen_date'").fetchone()

    last_date = row["value"] if row else cur_date
    if last_date != cur_date:
        cur.execute("UPDATE settings SET value = ? WHERE key = 'last_seen_date'", (cur_date,))
        cur.execute("UPDATE supervisors SET on_time = 0, arrived_at = ''")
        db.commit()

    students = cur.execute("SELECT id FROM students").fetchall()
    for st in students:
        cur.execute("""
            INSERT OR IGNORE INTO attendance (student_id, work_date, status, phone_status, phone_given)
            VALUES (?, ?, '', '', 0)
        """, (st["id"], cur_date))
    db.commit()


def is_time_in_shift(now_hm, start_hm, end_hm):
    if start_hm <= end_hm:
        return start_hm <= now_hm <= end_hm
    return now_hm >= start_hm or now_hm <= end_hm


def current_role():
    return session.get("role")


def active_theme():
    db = get_db()
    if session.get("manual_theme") in ("day", "night"):
        return session["manual_theme"]
    row = db.execute("SELECT value FROM settings WHERE key = 'auto_theme'").fetchone()
    auto_enabled = (row["value"] == "1") if row else True
    return auto_theme_by_hour() if auto_enabled else "day"


def render_page(page_name):
    ensure_day_rollover()
    db = get_db()
    role = current_role()
    theme = active_theme()
    device_mode = detect_device_mode()
    selected_date = request.args.get("date") or today_str()
    try:
        datetime.strptime(selected_date, "%Y-%m-%d")
    except ValueError:
        selected_date = today_str()

    class_filter = request.args.get("class_name", "ALL")
    room_code_filter = request.args.get("room_code", "ALL")

    now_hm = datetime.now().strftime("%H:%M")
    sup_rows = db.execute("SELECT * FROM supervisors ORDER BY slot_number").fetchall()
    supervisors = []
    active_duty_list = []
    for s in sup_rows:
        d = dict(s)
        on_duty = is_time_in_shift(now_hm, d["shift_start"], d["shift_end"])
        d["on_duty"] = on_duty
        supervisors.append(d)
        if on_duty:
            active_duty_list.append(f"{esc(d['teacher_name'])} ({esc(d['shift_start'])}-{esc(d['shift_end'])})")
    duty_banner_text = ", ".join(active_duty_list) if active_duty_list else "Hozir smena vaqtidan tashqari"

    all_students_raw = db.execute("SELECT id FROM students").fetchall()
    for s in all_students_raw:
        db.execute("""
            INSERT OR IGNORE INTO attendance (student_id, work_date, status, phone_status, phone_given)
            VALUES (?, ?, '', '', 0)
        """, (s["id"], selected_date))
    db.commit()

    rows = db.execute("""
        SELECT s.id, s.full_name, s.class_name, s.room_id,
               r.code AS room_code, r.sub_label AS room_sub_label, r.capacity AS room_capacity,
               COALESCE(a.status, '') AS status,
               COALESCE(a.reason_type, '') AS reason_type,
               COALESCE(a.reason_note, '') AS reason_note,
               COALESCE(a.phone_status, '') AS phone_status,
               COALESCE(a.phone_given, 0) AS phone_given,
               COALESCE(a.phone_photo, '') AS phone_photo,
               COALESCE(a.phone_time, '') AS phone_time
        FROM students s
        JOIN rooms r ON s.room_id = r.id
        LEFT JOIN attendance a ON a.student_id = s.id AND a.work_date = ?
        ORDER BY CAST(substr(r.code, 1, length(r.code)-1) AS INTEGER), r.capacity DESC, s.full_name
    """, (selected_date,)).fetchall()

    students = []
    for r in rows:
        d = dict(r)
        if not d["phone_status"] and d["phone_given"] == 1:
            d["phone_status"] = "Berildi"
        students.append(d)

    classes = sorted(list({st["class_name"] for st in students}))
    room_codes = [f"{i}c" for i in range(1, 13)]

    filtered_students = students
    if class_filter != "ALL":
        filtered_students = [st for st in filtered_students if st["class_name"] == class_filter]
    if room_code_filter != "ALL":
        filtered_students = [st for st in filtered_students if st["room_code"] == room_code_filter]

    total_count = len(students)
    present_count = sum(1 for st in students if st["status"] == "+")
    absent_count = sum(1 for st in students if st["status"] == "-")
    unmarked_count = total_count - present_count - absent_count

    phone_given_count = sum(1 for st in students if st["phone_status"] == "Berildi")
    phone_taken_count = sum(1 for st in students if st["phone_status"] == "Olingan")
    phone_not_given_count = sum(1 for st in students if st["phone_status"] == "Berilmadi")

    class_chips_html = "".join(
        f'<div class="chip"><strong>{esc(cname)}:</strong> {sum(1 for st in students if st["class_name"] == cname and st["status"] == "+")}</div>'
        for cname in classes
    )

    all_rooms = db.execute("""
        SELECT id, code, sub_label, capacity
        FROM rooms
        ORDER BY CAST(substr(code, 1, length(code)-1) AS INTEGER), capacity DESC
    """).fetchall()

    rooms_grouped = []
    for r in all_rooms:
        occupants = [st for st in students if st["room_id"] == r["id"]]
        rooms_grouped.append({
            "id": r["id"],
            "code": r["code"],
            "sub_label": r["sub_label"],
            "capacity": r["capacity"],
            "occupants": occupants,
            "occupied_count": len(occupants),
            "present_in_room": sum(1 for o in occupants if o["status"] == "+")
        })

    total_attendance_records = db.execute("SELECT COUNT(*) AS c FROM attendance WHERE status != ''").fetchone()["c"]
    total_photos = db.execute("SELECT COUNT(*) AS c FROM attendance WHERE phone_photo != ''").fetchone()["c"]
    auto_theme_row = db.execute("SELECT value FROM settings WHERE key = 'auto_theme'").fetchone()
    auto_theme_enabled = (auto_theme_row["value"] == "1") if auto_theme_row else True

    flash_html = ""
    for category, msg in get_flashed_messages(with_categories=True):
        flash_html += f'<div class="alert alert-{esc(category)}">{esc(msg)}</div>'

    role_badge_html = ""
    if role:
        r_label = {"ustoz": "Ustoz", "oshpaz": "Oshpaz", "superadmin": "Super Admin"}.get(role, role)
        role_badge_html = f'''
          <span class="role-pill role-{esc(role)}">{esc(r_label)}</span>
          <form method="POST" action="{url_for('logout')}" class="inline-form">
            <button type="submit" class="btn btn-outline btn-sm">Chiqish</button>
          </form>
        '''

    theme_btn_label = "Kechki rejim" if theme == "day" else "Kunduzgi rejim"
    theme_next_val = "night" if theme == "day" else "day"

    device_btn_label = "Kompyuter rejimi" if device_mode == "phone" else "Telefon rejimi"
    device_next_val = "desktop" if device_mode == "phone" else "phone"

    if page_name == "login":
        body_html = f"""
        <section class="login-wrapper">
          <div class="glass-card login-card">
            <h1>Tizimga kirish</h1>
            <p class="muted">Rolni tanlang va PIN-kodni kiriting.</p>
            <form method="POST" action="{url_for('login')}">
              <label class="field-label">Rolni tanlang</label>
              <div class="role-select-grid">
                <label class="role-option">
                  <input type="radio" name="role" value="ustoz" checked />
                  <span><strong>Ustoz</strong><small>Tarbiyachi</small></span>
                </label>
                <label class="role-option">
                  <input type="radio" name="role" value="oshpaz" />
                  <span><strong>Oshpaz</strong><small>Oshxona</small></span>
                </label>
                <label class="role-option">
                  <input type="radio" name="role" value="superadmin" />
                  <span><strong>Super Admin</strong><small>Nazorat</small></span>
                </label>
              </div>
              <label class="field-label" for="pin">PIN-kod</label>
              <input id="pin" type="password" name="pin" class="input" placeholder="PIN-kodni kiriting" required />
              <button type="submit" class="btn btn-primary full-width mt-12">Kirish</button>
            </form>
          </div>
        </section>
        """
    elif page_name == "chef":
        body_html = f"""
        <section class="chef-section glass-card">
          <div class="chef-date">{esc(format_uz_date(selected_date))}</div>
          <div class="chef-label">Yotoqxonada bor o'quvchilar soni</div>
          <div class="chef-big-number">{present_count} <span>nafar</span></div>
          <div class="chef-substats">
            <div>Jami: <strong>{total_count}</strong></div>
            <div>Yo'q (-): <strong>{absent_count}</strong></div>
            <div>Belgilanmagan: <strong>{unmarked_count}</strong></div>
          </div>
          <div class="chip-row mb-16">{class_chips_html}</div>
          <a href="{url_for('chef_page')}" class="btn btn-primary">Yangilash</a>
        </section>
        """
    else:
        super_tab = f'<a href="{url_for("superadmin_page", date=selected_date)}" class="nav-tab {"active" if page_name == "superadmin" else ""}">5. Super Admin</a>' if role == "superadmin" else ""
        today_btn = f'<a href="{url_for(request.endpoint, date=today_str())}" class="btn btn-primary btn-sm">Bugun</a>' if selected_date != today_str() else ""

        sub_content = ""
        if page_name == "attendance":
            class_opts = "".join(
                f'<option value="{esc(c)}" {"selected" if class_filter == c else ""}>{esc(c)}</option>'
                for c in classes
            )
            room_opts = "".join(
                f'<option value="{esc(rc)}" {"selected" if room_code_filter == rc else ""}>{esc(rc)}</option>'
                for rc in room_codes
            )
            rows_html = ""
            for idx, st in enumerate(filtered_students, start=1):
                active_cls = "active-row" if idx == 1 else ""
                p_cls = "is-plus" if st["status"] == "+" else ""
                m_cls = "is-minus" if st["status"] == "-" else ""
                tag_txt = "Bor" if st["status"] == "+" else ("Yo'q" if st["status"] == "-" else "—")
                r_disp = ""
                if st["status"] == "-":
                    r_disp = f'{esc(st["reason_type"])}: {esc(st["reason_note"])}' if st["reason_note"] else esc(st["reason_type"])
                note_hidden = "" if st["reason_type"] == "Boshqa sabab" else "hidden"
                rows_html += f"""
                <tr class="excel-row {active_cls}" tabindex="0" data-student-id="{st['id']}" data-status="{esc(st['status'])}" onclick="focusRow(this)">
                  <td>{idx}</td>
                  <td><strong>{esc(st['full_name'])}</strong></td>
                  <td>{esc(st['class_name'])}</td>
                  <td>{esc(st['room_code'])} <small>({st['room_capacity']} k.)</small></td>
                  <td>
                    <button type="button" class="cell-btn plus-btn {p_cls}" onclick="event.stopPropagation(); setRowPlus(this.closest('tr'))">+</button>
                    <button type="button" class="cell-btn minus-btn {m_cls}" onclick="event.stopPropagation(); openRowMinus(this.closest('tr'))">-</button>
                    <span class="status-tag" id="tag-{st['id']}">{tag_txt}</span>
                  </td>
                  <td>
                    <div id="reason-display-{st['id']}" class="reason-display">{r_disp}</div>
                    <div class="inline-reason-editor hidden" id="editor-{st['id']}" onclick="event.stopPropagation()">
                      <select class="input input-sm" id="rtype-{st['id']}" onchange="checkOtherInput({st['id']})">
                        <option value="Sababli" {"selected" if st["reason_type"] == "Sababli" else ""}>Sababli</option>
                        <option value="O'zboshimchalik bilan" {"selected" if st["reason_type"] == "O'zboshimchalik bilan" else ""}>O'zboshimchalik bilan</option>
                        <option value="Boshqa sabab" {"selected" if st["reason_type"] == "Boshqa sabab" else ""}>Boshqa sabab</option>
                      </select>
                      <input type="text" class="input input-sm {note_hidden}" id="rnote-{st['id']}" value="{esc(st['reason_note'])}" placeholder="Izoh..." />
                      <button type="button" class="btn btn-danger btn-sm" onclick="saveRowMinus({st['id']}, this.closest('tr'))">Saqlash &rarr;</button>
                    </div>
                  </td>
                </tr>
                """
            sub_content = f"""
            <section class="glass-card section-box">
              <div class="section-header">
                <div>
                  <h2>Excel Davomat ({esc(format_uz_date(selected_date))})</h2>
                  <p class="muted">Qatorni tanlang yoki &uarr;/&darr; bilan yuring: <strong>+</strong> bossangiz "Bor" bo'lib keyingi qatorga o'tadi, <strong>-</strong> bossangiz sabab ochiladi.</p>
                </div>
                <form method="GET" action="{url_for('attendance_page')}" class="filter-bar">
                  <input type="hidden" name="date" value="{esc(selected_date)}" />
                  <select name="class_name" class="input input-sm" onchange="this.form.submit()">
                    <option value="ALL" {"selected" if class_filter == "ALL" else ""}>Barcha sinflar</option>
                    {class_opts}
                  </select>
                  <select name="room_code" class="input input-sm" onchange="this.form.submit()">
                    <option value="ALL" {"selected" if room_code_filter == "ALL" else ""}>1c-12c barchasi</option>
                    {room_opts}
                  </select>
                </form>
              </div>
              <div class="table-wrap">
                <table class="excel-table" id="excel-attendance-table">
                  <thead>
                    <tr><th>#</th><th>O'quvchi</th><th>Sinf</th><th>Xona</th><th>+ / -</th><th>Sabab</th></tr>
                  </thead>
                  <tbody>{rows_html}</tbody>
                </table>
              </div>
            </section>
            """
        elif page_name == "phones":
            p_rows = ""
            for st in students:
                ps = st["phone_status"]
                if ps == "Berildi":
                    p_badge = f'<span class="badge badge-phone">Berildi ({esc(st["phone_time"])})</span>'
                elif ps == "Olingan":
                    p_badge = f'<span class="badge badge-taken">Olingan ({esc(st["phone_time"])})</span>'
                elif ps == "Berilmadi":
                    p_badge = f'<span class="badge badge-notgiven">Berilmadi ({esc(st["phone_time"])})</span>'
                else:
                    p_badge = '<span class="badge badge-none">Belgilanmagan</span>'

                p_img = f'<a href="{url_for("static", filename=st["phone_photo"])}" target="_blank" class="btn btn-soft btn-sm">Ko\'rish</a>' if st["phone_photo"] else "—"
                safe_name = esc(st["full_name"]).replace("'", "")

                p_rows += f"""
                <tr>
                  <td><strong>{esc(st['full_name'])}</strong></td>
                  <td>{esc(st['class_name'])} &middot; {esc(st['room_code'])}</td>
                  <td>{p_badge}</td>
                  <td>
                    <div class="phone-btn-group">
                      <button type="button" class="btn btn-primary btn-sm" onclick="openLiveCamera({st['id']}, '{safe_name}', 'Berildi')">Berildi (Kamera)</button>
                      <button type="button" class="btn btn-soft btn-sm" onclick="openLiveCamera({st['id']}, '{safe_name}', 'Olingan')">Olingan (Kamera)</button>
                      <form method="POST" action="{url_for('set_phone_status')}" class="inline-form">
                        <input type="hidden" name="student_id" value="{st['id']}" />
                        <input type="hidden" name="work_date" value="{esc(selected_date)}" />
                        <input type="hidden" name="phone_status" value="Berilmadi" />
                        <button type="submit" class="btn btn-outline btn-sm">Berilmadi</button>
                      </form>
                    </div>
                  </td>
                  <td>{p_img}</td>
                </tr>
                """
            sub_content = f"""
            <section class="glass-card section-box">
              <div class="section-header">
                <div>
                  <h2>Telefon Nazorati — Berildi / Olingan / Berilmadi</h2>
                  <p class="muted">Berildi yoki Olingan belgilanganda jonli kamera ochiladi. Berilmadi esa tepadan hammaga bir tugmada qo'yiladi.</p>
                </div>
                <form method="POST" action="{url_for('set_all_phones_not_given')}" onsubmit="return confirm('Ro\'yxatdagi barcha o\'quvchilarga \'Berilmadi\' belgilansinmi?');">
                  <input type="hidden" name="work_date" value="{esc(selected_date)}" />
                  <button type="submit" class="btn btn-danger">Berilmadi (Hammaga)</button>
                </form>
              </div>

              <div class="phone-counters mb-16">
                <span class="chip">Berildi: <strong>{phone_given_count}</strong></span>
                <span class="chip">Olingan: <strong>{phone_taken_count}</strong></span>
                <span class="chip">Berilmadi: <strong>{phone_not_given_count}</strong></span>
              </div>

              <div id="camera-modal" class="camera-panel hidden">
                <div class="camera-header">
                  <strong id="camera-target-name">Kamera</strong>
                  <button type="button" class="btn btn-outline btn-sm" onclick="closeCamera()">Yopish</button>
                </div>
                <div class="camera-viewport">
                  <video id="camera-video" autoplay playsinline></video>
                  <canvas id="camera-canvas" class="hidden"></canvas>
                </div>
                <div id="camera-error" class="alert alert-error hidden"></div>
                <div class="camera-actions">
                  <button type="button" class="btn btn-primary full-width" onclick="capturePhoto()">Rasmga olish va Tasdiqlash</button>
                </div>
                <form id="photo-submit-form" method="POST" action="{url_for('save_phone_photo')}" class="hidden">
                  <input type="hidden" name="student_id" id="photo-student-id" />
                  <input type="hidden" name="phone_status" id="photo-phone-status" value="Berildi" />
                  <input type="hidden" name="work_date" value="{esc(selected_date)}" />
                  <input type="hidden" name="photo_base64" id="photo-base64" />
                </form>
              </div>

              <div class="table-wrap">
                <table class="excel-table">
                  <thead><tr><th>O'quvchi</th><th>Sinf / Xona</th><th>Holat</th><th>Amallar</th><th>Isbot rasm</th></tr></thead>
                  <tbody>{p_rows}</tbody>
                </table>
              </div>
            </section>
            """
        elif page_name == "students":
            room_select_opts = ""
            for rg in rooms_grouped:
                dis = "disabled" if rg["occupied_count"] >= rg["capacity"] else ""
                room_select_opts += f'<option value="{rg["id"]}" {dis}>{esc(rg["code"])} — {esc(rg["sub_label"])} ({rg["occupied_count"]}/{rg["capacity"]})</option>'
            st_rows = ""
            for st in students:
                st_rows += f"""
                <tr>
                  <td>{esc(st['full_name'])}</td>
                  <td>{esc(st['class_name'])}</td>
                  <td>{esc(st['room_code'])} ({esc(st['room_sub_label'])})</td>
                  <td>
                    <form method="POST" action="{url_for('delete_student', student_id=st['id'])}" onsubmit="return confirm('O\'chirilsinmi?');">
                      <input type="hidden" name="work_date" value="{esc(selected_date)}" />
                      <button type="submit" class="btn btn-danger btn-sm">O'chirish</button>
                    </form>
                  </td>
                </tr>
                """
            sub_content = f"""
            <section class="glass-card section-box">
              <h2>O'quvchi Qo'shish va Ro'yxat</h2>
              <form method="POST" action="{url_for('add_student')}" class="form-grid mb-16">
                <input type="hidden" name="work_date" value="{esc(selected_date)}" />
                <div>
                  <label class="field-label">Ism-familiya</label>
                  <input type="text" name="full_name" class="input" required />
                </div>
                <div>
                  <label class="field-label">Sinf</label>
                  <input type="text" name="class_name" class="input" placeholder="Masalan: 7-A sinf" required />
                </div>
                <div>
                  <label class="field-label">Xona (1c-12c)</label>
                  <select name="room_id" class="input" required>{room_select_opts}</select>
                </div>
                <div class="align-end">
                  <button type="submit" class="btn btn-primary full-width">Qo'shish</button>
                </div>
              </form>
              <div class="table-wrap">
                <table class="excel-table">
                  <thead><tr><th>Ism-familiya</th><th>Sinf</th><th>Xona</th><th>Amal</th></tr></thead>
                  <tbody>{st_rows}</tbody>
                </table>
              </div>
            </section>
            """
        elif page_name == "rooms":
            r_cards = ""
            for rg in rooms_grouped:
                if rg["occupants"]:
                    lis = "".join(
                        f'<li><span>{esc(o["full_name"])} <small>({esc(o["class_name"])})</small></span><span class="mini-badge {"plus" if o["status"]=="+" else ("minus" if o["status"]=="-" else "wait")}">{esc(o["status"]) or "?"}</span></li>'
                        for o in rg["occupants"]
                    )
                    occ_html = f'<ul class="occupant-list">{lis}</ul>'
                else:
                    occ_html = '<p class="empty-room">Bo\'sh xona</p>'
                r_cards += f"""
                <div class="room-card">
                  <div class="room-card-top">
                    <span class="room-code-badge">{esc(rg['code'])}</span>
                    <span class="room-cap">{esc(rg['sub_label'])} &middot; <strong>{rg['occupied_count']}/{rg['capacity']}</strong></span>
                  </div>
                  <div class="room-present-note">Bor (+): <strong>{rg['present_in_room']}</strong></div>
                  {occ_html}
                </div>
                """
            sub_content = f"""
            <section class="glass-card section-box">
              <h2>Xonalar (1c - 12c) &middot; Har birida 6 kishilik va 4 kishilik</h2>
              <div class="rooms-grid mt-12">{r_cards}</div>
            </section>
            """
        elif page_name == "superadmin" and role == "superadmin":
            chk = "checked" if auto_theme_enabled else ""
            sup_cards_html = ""
            for sp in supervisors:
                duty_pill = '<span class="badge badge-phone">Hozir navbatchi</span>' if sp["on_duty"] else '<span class="badge badge-none">Navbatda emas</span>'
                ontime_pill = f'<span class="badge badge-plus">Ishiga o\'z vaqtida keldi ({esc(sp["arrived_at"])})</span>' if sp["on_time"] == 1 else '<span class="badge badge-none">Hali belgilanmagan</span>'
                sub_val = "0" if sp["on_time"] == 1 else "1"
                sub_lbl = "Belginini olish" if sp["on_time"] == 1 else "Ishiga o'z vaqtida keldi"
                sup_cards_html += f"""
                <div class="room-card">
                  <div class="room-card-top">
                    <span class="room-code-badge">{sp['slot_number']}-Navbat</span>
                    {duty_pill}
                  </div>
                  <div class="mt-12">{ontime_pill}</div>
                  <form method="POST" action="{url_for('superadmin_update_supervisor')}" class="mt-12">
                    <input type="hidden" name="slot_number" value="{sp['slot_number']}" />
                    <label class="field-label">Ustoz ismi</label>
                    <input type="text" name="teacher_name" class="input input-sm" value="{esc(sp['teacher_name'])}" required />