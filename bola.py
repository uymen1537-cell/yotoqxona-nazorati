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


def ensure_day_rollover():
    db = get_db()
    cur = db.cursor()
    cur_date = today_str()

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
                    <input type="text" name="teacher_name" value="{esc(sp['teacher_name'])}" class="input input-sm full-width mb-16" required />
                    <div class="form-grid mb-16">
                      <div>
                        <label class="field-label">Boshlanish</label>
                        <input type="time" name="shift_start" value="{esc(sp['shift_start'])}" class="input input-sm full-width" required />
                      </div>
                      <div>
                        <label class="field-label">Tugash</label>
                        <input type="time" name="shift_end" value="{esc(sp['shift_end'])}" class="input input-sm full-width" required />
                      </div>
                    </div>
                    <button type="submit" class="btn btn-primary btn-sm full-width">Smena va ismni saqlash</button>
                  </form>
                  <form method="POST" action="{url_for('superadmin_mark_ontime')}" class="mt-12">
                    <input type="hidden" name="slot_number" value="{sp['slot_number']}" />
                    <input type="hidden" name="on_time" value="{sub_val}" />
                    <button type="submit" class="btn btn-soft btn-sm full-width">{sub_lbl}</button>
                  </form>
                </div>
                """

            sub_content = f"""
            <section class="glass-card section-box">
              <h2>Super Admin Paneli</h2>
              <div class="duty-box mt-12 mb-16">
                <strong>Hozir kim bo'lishi kerak (vaqt bo'yicha):</strong> {duty_banner_text}
              </div>

              <h3>3 ta Ustoz Jadvali va Kelish Nazorati</h3>
              <div class="rooms-grid mt-12 mb-16">{sup_cards_html}</div>

              <div class="stats-grid">
                <div class="stat-card glass-card"><div class="stat-title">Davomat yozuvlari</div><div class="stat-value">{total_attendance_records}</div></div>
                <div class="stat-card glass-card"><div class="stat-title">Telefon rasmlari</div><div class="stat-value">{total_photos}</div></div>
                <div class="stat-card glass-card"><div class="stat-title">Xonalar</div><div class="stat-value">24</div><div class="stat-sub">1c-12c (6 va 4 kishilik)</div></div>
              </div>
              <div class="admin-panels">
                <form method="POST" action="{url_for('superadmin_settings')}" class="admin-box">
                  <h3>Kunduzgi / Kechki Rejim</h3>
                  <label class="checkbox-row">
                    <input type="checkbox" name="auto_theme" {chk} />
                    <span>Avtomatik o'tish (06:00-18:00 Kunduzgi, 18:00-06:00 Kechki)</span>
                  </label>
                  <button type="submit" class="btn btn-primary">Saqlash</button>
                </form>
                <div class="admin-box">
                  <h3>Hisobotni Yuklash (CSV)</h3>
                  <p class="muted">Sana: {esc(selected_date)}</p>
                  <a href="{url_for('superadmin_export_csv', date=selected_date)}" class="btn btn-soft">CSV yuklab olish</a>
                </div>
                <form method="POST" action="{url_for('superadmin_reset_day')}" class="admin-box" onsubmit="return confirm('Kun davomati tozalansinmi?');">
                  <h3>Kunni Tozalash</h3>
                  <input type="date" name="reset_date" value="{esc(selected_date)}" class="input input-sm" />
                  <button type="submit" class="btn btn-danger">Tozalash</button>
                </form>
              </div>
            </section>
            """

        body_html = f"""
        <nav class="subnav glass-card">
          <a href="{url_for('attendance_page', date=selected_date)}" class="nav-tab {'active' if page_name == 'attendance' else ''}">1. Davomat (Excel)</a>
          <a href="{url_for('phones_page', date=selected_date)}" class="nav-tab {'active' if page_name == 'phones' else ''}">2. Telefon Berilgani</a>
          <a href="{url_for('students_page', date=selected_date)}" class="nav-tab {'active' if page_name == 'students' else ''}">3. O'quvchi Qo'shish</a>
          <a href="{url_for('rooms_page', date=selected_date)}" class="nav-tab {'active' if page_name == 'rooms' else ''}">4. Xonalar (1c-12c)</a>
          {super_tab}
        </nav>
        <section class="date-bar glass-card">
          <form method="GET" action="{request.path}" class="date-form">
            <label for="date-input"><strong>Sana:</strong></label>
            <input id="date-input" type="date" name="date" value="{esc(selected_date)}" class="input input-sm" onchange="this.form.submit()" />
            {today_btn}
          </form>
          <div class="live-summary-bar">
            Navbatchi: <strong>{duty_banner_text}</strong> &middot;
            Jami: <strong id="sum-total">{total_count}</strong> &middot;
            Bor (+): <strong id="sum-present" class="txt-green">{present_count}</strong> &middot;
            Yo'q (-): <strong id="sum-absent" class="txt-red">{absent_count}</strong> &middot;
            Tel berildi: <strong id="sum-phones" class="txt-blue">{phone_given_count}</strong>
          </div>
        </section>
        {sub_content}
        """

    return f"""<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Yotoqxona Nazorati</title>
  <style>
    :root {{ --radius: 14px; --radius-sm: 9px; }}
    body.theme-day {{
      --bg: linear-gradient(135deg, #eef4ff 0%, #f8fafc 55%, #ecfdf5 100%);
      --card: rgba(255, 255, 255, 0.92);
      --border: rgba(15, 23, 42, 0.12);
      --text: #0f172a; --muted: #475569; --surface: #ffffff; --soft: #e2e8f0;
      --row-active: rgba(37, 99, 235, 0.13);
    }}
    body.theme-night {{
      --bg: linear-gradient(135deg, #070b14 0%, #0f172a 60%, #111827 100%);
      --card: rgba(15, 23, 42, 0.92);
      --border: rgba(255, 255, 255, 0.12);
      --text: #f8fafc; --muted: #94a3b8; --surface: #1e293b; --soft: #1e293b;
      --row-active: rgba(59, 130, 246, 0.24);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}
    .app-container {{ max-width: 1160px; margin: 0 auto; padding: 14px; }}
    .glass-card {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); }}
    .topbar {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; padding: 14px 18px; margin-bottom: 12px; }}
    .brand-title {{ font-size: 1.2rem; font-weight: 800; }}
    .date-badge {{ font-size: 0.88rem; color: var(--muted); }}
    .topbar-actions {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }}
    .inline-form {{ display: inline; }}
    .role-pill {{ padding: 5px 11px; border-radius: 999px; font-size: 0.8rem; font-weight: 700; background: #2563eb; color: #fff; }}
    .role-pill.role-oshpaz {{ background: #d97706; }}
    .role-pill.role-superadmin {{ background: #7c3aed; }}
    .btn {{ display: inline-flex; align-items: center; justify-content: center; padding: 9px 14px; border-radius: var(--radius-sm); border: none; font-weight: 600; font-size: 0.9rem; cursor: pointer; text-decoration: none; }}
    .btn-sm {{ padding: 6px 10px; font-size: 0.82rem; }}
    .full-width {{ width: 100%; }}
    .mt-12 {{ margin-top: 12px; }}
    .mb-16 {{ margin-bottom: 16px; }}
    .align-end {{ display: flex; align-items: flex-end; }}
    .btn-primary {{ background: #2563eb; color: #fff; }}
    .btn-soft {{ background: var(--soft); color: var(--text); }}
    .btn-outline {{ background: transparent; border: 1px solid var(--border); color: var(--text); }}
    .btn-danger {{ background: #dc2626; color: #fff; }}
    .input {{ width: 100%; padding: 9px 11px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); color: var(--text); }}
    .input-sm {{ width: auto; padding: 6px 9px; font-size: 0.85rem; }}
    .field-label {{ display: block; font-size: 0.84rem; font-weight: 600; color: var(--muted); margin-bottom: 5px; }}
    .muted {{ color: var(--muted); font-size: 0.88rem; margin: 4px 0 0; }}
    .txt-green {{ color: #16a34a; }}
    .txt-red {{ color: #dc2626; }}
    .txt-blue {{ color: #2563eb; }}
    .alerts {{ margin-bottom: 12px; }}
    .alert {{ padding: 10px 14px; border-radius: var(--radius-sm); margin-bottom: 6px; font-weight: 600; }}
    .alert-success {{ background: rgba(22, 163, 74, 0.16); color: #16a34a; }}
    .alert-error {{ background: rgba(220, 38, 38, 0.16); color: #dc2626; }}
    .alert-info {{ background: rgba(37, 99, 235, 0.16); color: #2563eb; }}
    .login-wrapper {{ display: flex; justify-content: center; padding: 24px 0; }}
    .login-card {{ width: 100%; max-width: 460px; padding: 24px; }}
    .role-select-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px; }}
    .role-option input {{ display: none; }}
    .role-option span {{ display: flex; flex-direction: column; align-items: center; padding: 12px 6px; border: 1.5px solid var(--border); border-radius: var(--radius-sm); cursor: pointer; }}
    .role-option input:checked + span {{ border-color: #2563eb; background: rgba(37, 99, 235, 0.14); }}
    .chef-section {{ max-width: 640px; margin: 20px auto; padding: 32px 20px; text-align: center; }}
    .chef-big-number {{ font-size: 4.2rem; font-weight: 900; color: #16a34a; margin: 12px 0; }}
    .chef-big-number span {{ font-size: 1.3rem; color: var(--muted); }}
    .chef-substats {{ display: flex; justify-content: center; gap: 16px; flex-wrap: wrap; color: var(--muted); margin-bottom: 18px; }}
    .chip-row {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }}
    .chip {{ padding: 6px 12px; border-radius: 999px; background: var(--soft); font-size: 0.88rem; }}
    .subnav {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 8px; margin-bottom: 12px; }}
    .nav-tab {{ padding: 8px 12px; border-radius: var(--radius-sm); text-decoration: none; color: var(--text); font-weight: 600; font-size: 0.9rem; }}
    .nav-tab.active {{ background: #2563eb; color: #fff; }}
    .date-bar {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; padding: 10px 16px; margin-bottom: 12px; }}
    .date-form {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }}
    .live-summary-bar {{ font-size: 0.88rem; }}
    .duty-box {{ padding: 12px 14px; border-radius: var(--radius-sm); background: rgba(37, 99, 235, 0.12); border: 1px solid rgba(37, 99, 235, 0.25); }}
    .section-box {{ padding: 18px; }}
    .section-header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 14px; }}
    .section-header h2 {{ margin: 0; }}
    .filter-bar {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .table-wrap {{ overflow-x: auto; }}
    .excel-table {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: var(--radius-sm); overflow: hidden; }}
    .excel-table th, .excel-table td {{ padding: 9px 11px; border: 1px solid var(--border); text-align: left; }}
    .excel-table th {{ background: var(--soft); font-size: 0.85rem; }}
    .excel-row {{ cursor: pointer; outline: none; }}
    .excel-row.active-row {{ background: var(--row-active); box-shadow: inset 3px 0 0 #2563eb; }}
    .cell-btn {{ width: 34px; height: 30px; border-radius: 6px; border: 1px solid var(--border); font-weight: 800; font-size: 1rem; cursor: pointer; background: var(--soft); color: var(--text); }}
    .cell-btn.is-plus {{ background: #16a34a; color: #fff; border-color: #16a34a; }}
    .cell-btn.is-minus {{ background: #dc2626; color: #fff; border-color: #dc2626; }}
    .status-tag {{ margin-left: 6px; font-weight: 700; font-size: 0.85rem; }}
    .inline-reason-editor {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; align-items: center; }}
    .reason-display {{ font-size: 0.84rem; color: var(--muted); }}
    .badge {{ padding: 3px 9px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; }}
    .badge-plus {{ background: rgba(22, 163, 74, 0.16); color: #16a34a; }}
    .badge-phone {{ background: rgba(37, 99, 235, 0.16); color: #2563eb; }}
    .badge-taken {{ background: rgba(217, 119, 6, 0.18); color: #d97706; }}
    .badge-notgiven {{ background: rgba(220, 38, 38, 0.16); color: #dc2626; }}
    .badge-none {{ background: var(--soft); color: var(--muted); }}
    .phone-btn-group {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
    .phone-counters {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .camera-panel {{ padding: 14px; margin-bottom: 14px; border: 1.5px solid #2563eb; border-radius: var(--radius-sm); background: var(--surface); }}
    .camera-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
    .camera-viewport video {{ width: 100%; max-height: 340px; border-radius: var(--radius-sm); background: #000; }}
    .camera-actions {{ margin-top: 10px; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
    .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin-bottom: 14px; }}
    .stat-card {{ padding: 14px; }}
    .stat-title {{ font-size: 0.82rem; color: var(--muted); }}
    .stat-value {{ font-size: 1.8rem; font-weight: 800; margin-top: 4px; }}
    .stat-sub {{ font-size: 0.78rem; color: var(--muted); }}
    .rooms-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }}
    .room-card {{ padding: 12px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); }}
    .room-card-top {{ display: flex; justify-content: space-between; align-items: center; }}
    .room-code-badge {{ background: #2563eb; color: #fff; padding: 2px 9px; border-radius: 7px; font-weight: 800; }}
    .room-cap {{ font-size: 0.82rem; color: var(--muted); }}
    .room-present-note {{ font-size: 0.84rem; color: #16a34a; font-weight: 700; margin-top: 6px; }}
    .occupant-list {{ list-style: none; padding: 0; margin: 8px 0 0; }}
    .occupant-list li {{ display: flex; justify-content: space-between; padding: 5px 0; border-top: 1px dashed var(--border); font-size: 0.88rem; }}
    .mini-badge {{ padding: 1px 6px; border-radius: 5px; font-weight: 800; font-size: 0.76rem; }}
    .mini-badge.plus {{ background: rgba(22, 163, 74, 0.2); color: #16a34a; }}
    .mini-badge.minus {{ background: rgba(220, 38, 38, 0.2); color: #dc2626; }}
    .mini-badge.wait {{ background: var(--soft); color: var(--muted); }}
    .empty-room {{ font-size: 0.82rem; color: var(--muted); margin-top: 8px; }}
    .admin-panels {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px; }}
    .admin-box {{ padding: 14px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); display: flex; flex-direction: column; gap: 8px; }}
    .checkbox-row {{ display: flex; gap: 8px; align-items: flex-start; font-size: 0.88rem; }}
    .hidden {{ display: none !important; }}

    /* Telefon rejimi (majburiy yoki kichik ekran) */
    body.mode-phone .app-container {{ max-width: 540px; padding: 10px; }}
    body.mode-phone .topbar {{ padding: 12px; }}
    body.mode-phone .subnav {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }}
    body.mode-phone .nav-tab {{ text-align: center; padding: 10px 8px; font-size: 0.85rem; }}
    body.mode-phone .section-box {{ padding: 14px; }}
    body.mode-phone .cell-btn {{ width: 42px; height: 38px; font-size: 1.15rem; }}
    body.mode-phone .btn {{ min-height: 40px; }}
    body.mode-phone .btn-sm {{ min-height: 36px; padding: 8px 10px; font-size: 0.84rem; }}
    body.mode-phone .phone-btn-group {{ flex-direction: column; align-items: stretch; }}
    body.mode-phone .role-select-grid {{ grid-template-columns: 1fr; }}
    body.mode-phone .rooms-grid, body.mode-phone .admin-panels, body.mode-phone .stats-grid {{ grid-template-columns: 1fr; }}
    body.mode-phone .chef-big-number {{ font-size: 3.3rem; }}

    @media (max-width: 680px) {{
      .app-container {{ padding: 10px; }}
      .subnav {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }}
      .nav-tab {{ text-align: center; padding: 10px 8px; font-size: 0.85rem; }}
      .cell-btn {{ width: 40px; height: 36px; }}
      .phone-btn-group {{ flex-direction: column; align-items: stretch; }}
      .role-select-grid {{ grid-template-columns: 1fr; }}
      .rooms-grid, .admin-panels, .stats-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body class="theme-{theme} mode-{device_mode}">
  <div class="app-container">
    <header class="topbar glass-card">
      <div>
        <div class="brand-title">Yotoqxona Nazorati</div>
        <div class="date-badge">Bugun: <strong>{esc(format_uz_date(today_str()))}</strong> &middot; {datetime.now().strftime("%H:%M")}</div>
      </div>
      <div class="topbar-actions">
        <form method="POST" action="{url_for('toggle_device_mode')}" class="inline-form">
          <input type="hidden" name="next_url" value="{esc(request.full_path)}" />
          <input type="hidden" name="device_mode" value="{device_next_val}" />
          <button type="submit" class="btn btn-outline btn-sm">{device_btn_label}</button>
        </form>
        <form method="POST" action="{url_for('toggle_theme')}" class="inline-form">
          <input type="hidden" name="next_url" value="{esc(request.full_path)}" />
          <input type="hidden" name="theme" value="{theme_next_val}" />
          <button type="submit" class="btn btn-soft btn-sm">{theme_btn_label}</button>
        </form>
        {role_badge_html}
      </div>
    </header>
    <div class="alerts">{flash_html}</div>
    {body_html}
  </div>
  <script>
    const CURRENT_DATE = "{esc(selected_date)}";
    let cameraStream = null;

    function getRows() {{
      return Array.from(document.querySelectorAll("#excel-attendance-table tbody tr.excel-row"));
    }}
    function focusRow(row) {{
      if (!row) return;
      getRows().forEach(r => r.classList.remove("active-row"));
      row.classList.add("active-row");
      row.focus();
      row.scrollIntoView({{ block: "nearest", behavior: "smooth" }});
    }}
    function moveNextRow(currentRow) {{
      const rows = getRows();
      const idx = rows.indexOf(currentRow);
      if (idx >= 0 && idx + 1 < rows.length) focusRow(rows[idx + 1]);
    }}
    function movePrevRow(currentRow) {{
      const rows = getRows();
      const idx = rows.indexOf(currentRow);
      if (idx > 0) focusRow(rows[idx - 1]);
    }}
    function recountStats() {{
      const rows = getRows();
      if (!rows.length) return;
      const plusCnt = rows.filter(r => r.dataset.status === "+").length;
      const minusCnt = rows.filter(r => r.dataset.status === "-").length;
      const pEl = document.getElementById("sum-present");
      const aEl = document.getElementById("sum-absent");
      if (pEl) pEl.textContent = plusCnt;
      if (aEl) aEl.textContent = minusCnt;
    }}
    async function postAttendance(studentId, status, reasonType = "", reasonNote = "") {{
      const fd = new FormData();
      fd.append("student_id", studentId);
      fd.append("work_date", CURRENT_DATE);
      fd.append("status", status);
      fd.append("reason_type", reasonType);
      fd.append("reason_note", reasonNote);
      const res = await fetch("{url_for('mark_attendance')}", {{
        method: "POST",
        headers: {{ "X-Excel-Row": "1" }},
        body: fd
      }});
      return res.ok;
    }}
    async function setRowPlus(row) {{
      if (!row) return;
      const sid = row.dataset.studentId;
      const ok = await postAttendance(sid, "+", "", "");
      if (!ok) return;
      row.dataset.status = "+";
      row.querySelector(".plus-btn").classList.add("is-plus");
      row.querySelector(".minus-btn").classList.remove("is-minus");
      document.getElementById("tag-" + sid).textContent = "Bor";
      document.getElementById("reason-display-" + sid).textContent = "";
      document.getElementById("editor-" + sid).classList.add("hidden");
      recountStats();
      moveNextRow(row);
    }}
    function openRowMinus(row) {{
      if (!row) return;
      focusRow(row);
      const sid = row.dataset.studentId;
      document.getElementById("editor-" + sid).classList.remove("hidden");
      checkOtherInput(sid);
      document.getElementById("rtype-" + sid).focus();
    }}
    function checkOtherInput(sid) {{
      const sel = document.getElementById("rtype-" + sid);
      const note = document.getElementById("rnote-" + sid);
      if (sel && note) {{
        if (sel.value === "Boshqa sabab") note.classList.remove("hidden");
        else {{ note.classList.add("hidden"); note.value = ""; }}
      }}
    }}
    async function saveRowMinus(sid, row) {{
      const rtype = document.getElementById("rtype-" + sid).value;
      const rnote = document.getElementById("rnote-" + sid).value.trim();
      if (rtype === "Boshqa sabab" && !rnote) {{
        alert("'Boshqa sabab' uchun qisqa izoh yozing!");
        return;
      }}
      const ok = await postAttendance(sid, "-", rtype, rnote);
      if (!ok) return;
      row.dataset.status = "-";
      row.querySelector(".minus-btn").classList.add("is-minus");
      row.querySelector(".plus-btn").classList.remove("is-plus");
      document.getElementById("tag-" + sid).textContent = "Yo'q";
      document.getElementById("reason-display-" + sid).textContent = rnote ? (rtype + ": " + rnote) : rtype;
      document.getElementById("editor-" + sid).classList.add("hidden");
      recountStats();
      moveNextRow(row);
    }}
    document.addEventListener("keydown", function (e) {{
      const active = document.activeElement;
      if (active && (active.tagName === "INPUT" || active.tagName === "SELECT" || active.tagName === "TEXTAREA")) return;
      const row = document.querySelector("#excel-attendance-table tbody tr.excel-row.active-row");
      if (!row) return;
      if (e.key === "+" || e.key === "=") {{ e.preventDefault(); setRowPlus(row); }}
      else if (e.key === "-") {{ e.preventDefault(); openRowMinus(row); }}
      else if (e.key === "ArrowDown") {{ e.preventDefault(); moveNextRow(row); }}
      else if (e.key === "ArrowUp") {{ e.preventDefault(); movePrevRow(row); }}
    }});
    async function openLiveCamera(studentId, studentName, actionType = "Berildi") {{
      const modal = document.getElementById("camera-modal");
      const targetName = document.getElementById("camera-target-name");
      const studentInput = document.getElementById("photo-student-id");
      const statusInput = document.getElementById("photo-phone-status");
      const video = document.getElementById("camera-video");
      const errorBox = document.getElementById("camera-error");
      errorBox.classList.add("hidden");
      targetName.textContent = "Kamera (" + actionType + "): " + studentName;
      studentInput.value = studentId;
      if (statusInput) statusInput.value = actionType;
      modal.classList.remove("hidden");
      if (cameraStream) cameraStream.getTracks().forEach(t => t.stop());
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
        errorBox.textContent = "Kamera faqat HTTPS yoki localhost da ishlaydi.";
        errorBox.classList.remove("hidden");
        return;
      }}
      try {{
        cameraStream = await navigator.mediaDevices.getUserMedia({{ video: {{ facingMode: {{ ideal: "environment" }} }}, audio: false }});
        video.srcObject = cameraStream;
      }} catch (err) {{
        errorBox.textContent = "Kamera xatosi: " + err.message;
        errorBox.classList.remove("hidden");
      }}
    }}
    function capturePhoto() {{
      const video = document.getElementById("camera-video");
      const canvas = document.getElementById("camera-canvas");
      const photoInput = document.getElementById("photo-base64");
      const form = document.getElementById("photo-submit-form");
      if (!video.videoWidth || !video.videoHeight) return;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const now = new Date();
      const stamp = now.toLocaleDateString("uz-UZ") + " " + now.toTimeString().slice(0, 5);
      ctx.fillStyle = "rgba(0,0,0,0.65)";
      ctx.fillRect(10, canvas.height - 40, 270, 30);
      ctx.fillStyle = "#fff";
      ctx.font = "bold 15px sans-serif";
      ctx.fillText(stamp, 18, canvas.height - 20);
      photoInput.value = canvas.toDataURL("image/jpeg", 0.82);
      closeCamera();
      form.submit();
    }}
    function closeCamera() {{
      const modal = document.getElementById("camera-modal");
      const video = document.getElementById("camera-video");
      if (cameraStream) {{ cameraStream.getTracks().forEach(t => t.stop()); cameraStream = null; }}
      if (video) video.srcObject = null;
      if (modal) modal.classList.add("hidden");
    }}
  </script>
</body>
</html>"""


@app.route("/", methods=["GET"])
def index():
    role = current_role()
    if not role:
        return render_page("login")
    if role == "oshpaz":
        return redirect(url_for("chef_page"))
    return redirect(url_for("attendance_page"))


@app.route("/chef", methods=["GET"])
def chef_page():
    if current_role() != "oshpaz":
        return redirect(url_for("index"))
    return render_page("chef")


@app.route("/attendance", methods=["GET"])
def attendance_page():
    if current_role() not in ("ustoz", "superadmin"):
        return redirect(url_for("index"))
    return render_page("attendance")


@app.route("/phones", methods=["GET"])
def phones_page():
    if current_role() not in ("ustoz", "superadmin"):
        return redirect(url_for("index"))
    return render_page("phones")


@app.route("/students", methods=["GET"])
def students_page():
    if current_role() not in ("ustoz", "superadmin"):
        return redirect(url_for("index"))
    return render_page("students")


@app.route("/rooms", methods=["GET"])
def rooms_page():
    if current_role() not in ("ustoz", "superadmin"):
        return redirect(url_for("index"))
    return render_page("rooms")


@app.route("/superadmin", methods=["GET"])
def superadmin_page():
    if current_role() != "superadmin":
        return redirect(url_for("index"))
    return render_page("superadmin")


@app.route("/login", methods=["POST"])
def login():
    ip = get_client_ip()
    locked, wait_sec = is_login_locked(ip)
    if locked:
        flash(f"Ko'p urinish bo'ldi. {wait_sec} soniyadan keyin qayta urining.", "error")
        return redirect(url_for("index"))

    role = request.form.get("role", "").strip()
    pin = request.form.get("pin", "").strip()
    if role in PINS and pin == PINS[role]:
        clear_failed_login(ip)
        saved_mode = session.get("device_mode")
        saved_theme = session.get("manual_theme")
        session.clear()
        session["role"] = role
        if saved_mode:
            session["device_mode"] = saved_mode
        if saved_theme:
            session["manual_theme"] = saved_theme
        flash(f"{role.capitalize()} sifatida kirdingiz.", "success")
        if role == "oshpaz":
            return redirect(url_for("chef_page"))
        return redirect(url_for("attendance_page"))

    record_failed_login(ip)
    flash("PIN-kod noto'g'ri!", "error")
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    saved_mode = session.get("device_mode")
    saved_theme = session.get("manual_theme")
    session.clear()
    if saved_mode:
        session["device_mode"] = saved_mode
    if saved_theme:
        session["manual_theme"] = saved_theme
    flash("Tizimdan chiqdingiz.", "info")
    return redirect(url_for("index"))


@app.route("/toggle-device-mode", methods=["POST"])
def toggle_device_mode():
    target = request.form.get("device_mode")
    if target in ("phone", "desktop"):
        session["device_mode"] = target
    next_url = request.form.get("next_url") or url_for("index")
    if not next_url.startswith("/"):
        next_url = url_for("index")
    return redirect(next_url)


@app.route("/toggle-theme", methods=["POST"])
def toggle_theme():
    target = request.form.get("theme")
    if target in ("day", "night"):
        session["manual_theme"] = target
    else:
        session.pop("manual_theme", None)
    next_url = request.form.get("next_url") or url_for("index")
    if not next_url.startswith("/"):
        next_url = url_for("index")
    return redirect(next_url)


@app.route("/mark-attendance", methods=["POST"])
def mark_attendance():
    if current_role() not in ("ustoz", "superadmin"):
        return ("Ruxsat yo'q", 403)
    db = get_db()
    student_id = request.form.get("student_id", type=int)
    work_date = request.form.get("work_date") or today_str()
    try:
        datetime.strptime(work_date, "%Y-%m-%d")
    except ValueError:
        work_date = today_str()

    status = request.form.get("status", "").strip()
    reason_type = request.form.get("reason_type", "").strip()
    reason_note = request.form.get("reason_note", "").strip()[:200]
    if not student_id or status not in ("+", "-"):
        return ("Noto'g'ri ma'lumot", 400)
    if status == "+":
        reason_type = ""
        reason_note = ""
    else:
        if reason_type not in ("Sababli", "O'zboshimchalik bilan", "Boshqa sabab"):
            return ("Sabab tanlanmagan", 400)
        if reason_type == "Boshqa sabab" and not reason_note:
            return ("Izoh yozilmagan", 400)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("""
        INSERT INTO attendance (student_id, work_date, status, reason_type, reason_note, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(student_id, work_date) DO UPDATE SET
            status = excluded.status,
            reason_type = excluded.reason_type,
            reason_note = excluded.reason_note,
            updated_at = excluded.updated_at
    """, (student_id, work_date, status, reason_type, reason_note, now_str))
    db.commit()
    if request.headers.get("X-Excel-Row") == "1":
        return ("OK", 200)
    flash("Davomat saqlandi.", "success")
    return redirect(url_for("attendance_page", date=work_date))


@app.route("/set-phone-status", methods=["POST"])
def set_phone_status():
    if current_role() not in ("ustoz", "superadmin"):
        flash("Ruxsat yo'q!", "error")
        return redirect(url_for("index"))
    db = get_db()
    student_id = request.form.get("student_id", type=int)
    work_date = request.form.get("work_date") or today_str()
    p_status = request.form.get("phone_status", "").strip()
    if not student_id or p_status not in ("Berildi", "Olingan", "Berilmadi"):
        flash("Telefon holati noto'g'ri!", "error")
        return redirect(url_for("phones_page", date=work_date))
    taken_time = datetime.now().strftime("%H:%M")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p_given = 1 if p_status == "Berildi" else 0
    db.execute("""
        INSERT INTO attendance (student_id, work_date, phone_status, phone_given, phone_time, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(student_id, work_date) DO UPDATE SET
            phone_status = excluded.phone_status,
            phone_given = excluded.phone_given,
            phone_time = excluded.phone_time,
            updated_at = excluded.updated_at
    """, (student_id, work_date, p_status, p_given, taken_time, now_str))
    db.commit()
    flash(f"Telefon holati '{p_status}' deb belgilandi.", "success")
    return redirect(url_for("phones_page", date=work_date))


@app.route("/set-all-phones-not-given", methods=["POST"])
def set_all_phones_not_given():
    if current_role() not in ("ustoz", "superadmin"):
        flash("Ruxsat yo'q!", "error")
        return redirect(url_for("index"))
    db = get_db()
    work_date = request.form.get("work_date") or today_str()
    taken_time = datetime.now().strftime("%H:%M")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    students = db.execute("SELECT id FROM students").fetchall()
    for s in students:
        db.execute("""
            INSERT INTO attendance (student_id, work_date, phone_status, phone_given, phone_time, updated_at)
            VALUES (?, ?, 'Berilmadi', 0, ?, ?)
            ON CONFLICT(student_id, work_date) DO UPDATE SET
                phone_status = 'Berilmadi',
                phone_given = 0,
                phone_time = excluded.phone_time,
                updated_at = excluded.updated_at
        """, (s["id"], work_date, taken_time, now_str))
    db.commit()
    flash("Barcha o'quvchilarga 'Berilmadi' belgilandi.", "info")
    return redirect(url_for("phones_page", date=work_date))


@app.route("/save-phone-photo", methods=["POST"])
def save_phone_photo():
    if current_role() not in ("ustoz", "superadmin"):
        flash("Ruxsat yo'q!", "error")
        return redirect(url_for("index"))
    db = get_db()
    student_id = request.form.get("student_id", type=int)
    work_date = request.form.get("work_date") or today_str()
    p_status = request.form.get("phone_status", "Berildi").strip()
    if p_status not in ("Berildi", "Olingan"):
        p_status = "Berildi"
    photo_data = request.form.get("photo_base64", "").strip()
    if not student_id or not photo_data.startswith("data:image/jpeg;base64,"):
        flash("Kamera orqali rasm olinmadi!", "error")
        return redirect(url_for("phones_page", date=work_date))
    try:
        _, encoded = photo_data.split(",", 1)
        img_bytes = base64.b64decode(encoded, validate=True)
        if not img_bytes or len(img_bytes) > 5 * 1024 * 1024:
            raise ValueError("Invalid image size")
    except Exception:
        flash("Rasmni saqlashda xatolik!", "error")
        return redirect(url_for("phones_page", date=work_date))

    filename = f"phone_{int(student_id)}_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}.jpg"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        f.write(img_bytes)
    rel_path = f"uploads/{filename}"
    taken_time = datetime.now().strftime("%H:%M")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p_given = 1 if p_status == "Berildi" else 0
    db.execute("""
        INSERT INTO attendance (student_id, work_date, phone_status, phone_given, phone_photo, phone_time, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(student_id, work_date) DO UPDATE SET
            phone_status = excluded.phone_status,
            phone_given = excluded.phone_given,
            phone_photo = excluded.phone_photo,
            phone_time = excluded.phone_time,
            updated_at = excluded.updated_at
    """, (student_id, work_date, p_status, p_given, rel_path, taken_time, now_str))
    db.commit()
    flash(f"'{p_status}' deb belgilandi va rasm saqlandi ({taken_time}).", "success")
    return redirect(url_for("phones_page", date=work_date))


@app.route("/add-student", methods=["POST"])
def add_student():
    if current_role() not in ("ustoz", "superadmin"):
        flash("Ruxsat yo'q!", "error")
        return redirect(url_for("index"))
    db = get_db()
    full_name = request.form.get("full_name", "").strip()[:100]
    class_name = request.form.get("class_name", "").strip()[:40]
    room_id = request.form.get("room_id", type=int)
    work_date = request.form.get("work_date") or today_str()
    if not full_name or not class_name or not room_id:
        flash("Maydonlarni to'ldiring!", "error")
        return redirect(url_for("students_page", date=work_date))
    room = db.execute("SELECT id, code, sub_label, capacity FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if not room:
        flash("Xona topilmadi!", "error")
        return redirect(url_for("students_page", date=work_date))
    cur_count = db.execute("SELECT COUNT(*) AS c FROM students WHERE room_id = ?", (room_id,)).fetchone()["c"]
    if cur_count >= room["capacity"]:
        flash(f"{room['code']} ({room['sub_label']}) to'lgan ({cur_count}/{room['capacity']})!", "error")
        return redirect(url_for("students_page", date=work_date))
    cur = db.cursor()
    cur.execute("INSERT INTO students (full_name, class_name, room_id) VALUES (?, ?, ?)", (full_name, class_name, room_id))
    new_id = cur.lastrowid
    cur.execute("INSERT OR IGNORE INTO attendance (student_id, work_date, status, phone_status, phone_given) VALUES (?, ?, '', '', 0)", (new_id, work_date))
    db.commit()
    flash(f"{full_name} {room['code']} xonaga qo'shildi.", "success")
    return redirect(url_for("students_page", date=work_date))


@app.route("/delete-student/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if current_role() not in ("ustoz", "superadmin"):
        flash("Ruxsat yo'q!", "error")
        return redirect(url_for("index"))
    db = get_db()
    work_date = request.form.get("work_date") or today_str()
    db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    db.commit()
    flash("O'quvchi o'chirildi.", "info")
    return redirect(url_for("students_page", date=work_date))


@app.route("/superadmin/update-supervisor", methods=["POST"])
def superadmin_update_supervisor():
    if current_role() != "superadmin":
        flash("Faqat Super Admin uchun!", "error")
        return redirect(url_for("index"))
    db = get_db()
    slot_number = request.form.get("slot_number", type=int)
    teacher_name = request.form.get("teacher_name", "").strip()[:80]
    shift_start = request.form.get("shift_start", "").strip()
    shift_end = request.form.get("shift_end", "").strip()
    if slot_number in (1, 2, 3) and teacher_name and len(shift_start) == 5 and len(shift_end) == 5:
        db.execute("""
            UPDATE supervisors
            SET teacher_name = ?, shift_start = ?, shift_end = ?
            WHERE slot_number = ?
        """, (teacher_name, shift_start, shift_end, slot_number))
        db.commit()
        flash(f"{slot_number}-navbat ustoz ma'lumotlari saqlandi.", "success")
    return redirect(url_for("superadmin_page"))


@app.route("/superadmin/mark-ontime", methods=["POST"])
def superadmin_mark_ontime():
    if current_role() != "superadmin":
        flash("Faqat Super Admin uchun!", "error")
        return redirect(url_for("index"))
    db = get_db()
    slot_number = request.form.get("slot_number", type=int)
    on_time = 1 if request.form.get("on_time") == "1" else 0
    arrived_at = datetime.now().strftime("%H:%M") if on_time == 1 else ""
    if slot_number in (1, 2, 3):
        db.execute("""
            UPDATE supervisors
            SET on_time = ?, arrived_at = ?
            WHERE slot_number = ?
        """, (on_time, arrived_at, slot_number))
        db.commit()
        flash("Ustoz kelish holati yangilandi.", "success")
    return redirect(url_for("superadmin_page"))


@app.route("/superadmin/settings", methods=["POST"])
def superadmin_settings():
    if current_role() != "superadmin":
        flash("Faqat Super Admin uchun!", "error")
        return redirect(url_for("index"))
    db = get_db()
    auto_val = "1" if request.form.get("auto_theme") == "on" else "0"
    db.execute("UPDATE settings SET value = ? WHERE key = 'auto_theme'", (auto_val,))
    session.pop("manual_theme", None)
    db.commit()
    flash("Sozlama saqlandi.", "success")
    return redirect(url_for("superadmin_page"))


@app.route("/superadmin/reset-day", methods=["POST"])
def superadmin_reset_day():
    if current_role() != "superadmin":
        flash("Faqat Super Admin uchun!", "error")
        return redirect(url_for("index"))
    db = get_db()
    target_date = request.form.get("reset_date") or today_str()
    db.execute("DELETE FROM attendance WHERE work_date = ?", (target_date,))
    for s in db.execute("SELECT id FROM students").fetchall():
        db.execute("INSERT INTO attendance (student_id, work_date, status, phone_status, phone_given) VALUES (?, ?, '', '', 0)", (s["id"], target_date))
    db.commit()
    flash(f"{target_date} davomati tozalandi.", "info")
    return redirect(url_for("superadmin_page", date=target_date))


@app.route("/superadmin/export-csv", methods=["GET"])
def superadmin_export_csv():
    if current_role() != "superadmin":
        return redirect(url_for("index"))
    db = get_db()
    target_date = request.args.get("date") or today_str()
    rows = db.execute("""
        SELECT s.full_name, s.class_name, r.code, r.sub_label,
               COALESCE(a.status, '') AS status,
               COALESCE(a.reason_type, '') AS reason_type,
               COALESCE(a.reason_note, '') AS reason_note,
               COALESCE(a.phone_status, '') AS phone_status,
               COALESCE(a.phone_time, '') AS phone_time
        FROM students s
        JOIN rooms r ON s.room_id = r.id
        LEFT JOIN attendance a ON a.student_id = s.id AND a.work_date = ?
        ORDER BY r.code, s.full_name
    """, (target_date,)).fetchall()
    lines = ["Sana,Ism-familiya,Sinf,Xona,Xona turi,Holat,Sabab,Izoh,Telefon holati,Vaqt"]
    for r in rows:
        line = f'"{target_date}","{r["full_name"]}","{r["class_name"]}","{r["code"]}","{r["sub_label"]}","{r["status"]}","{r["reason_type"]}","{r["reason_note"]}","{r["phone_status"]}","{r["phone_time"]}"'
        lines.append(line)
    resp = make_response("\n".join(lines))
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename=davomat_{target_date}.csv"
    return resp


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)