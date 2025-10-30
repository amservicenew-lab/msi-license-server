from flask import Flask, request, jsonify
import sqlite3
import datetime
import os
import secrets
from pathlib import Path

app = Flask(__name__)

# ==============================
# ⚙️ KONFIGURASI
# ==============================
DB_NAME = os.environ.get("DB_NAME", "licenses.db")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "super-long-admin-token-xyz")  # Ganti di ENV Render

# ==============================
# 🧱 INISIALISASI DATABASE
# ==============================
def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            user TEXT DEFAULT 'unknown',
            hwid TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'VALID',
            expire DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Database siap digunakan:", DB_NAME)

# ==============================
# 🛡️ ADMIN TOKEN VALIDATOR
# ==============================
def require_admin(req):
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token = auth.split("Bearer ")[1].strip()
    return token == ADMIN_TOKEN

# ==============================
# 🔍 CEK LISENSI VIA HWID
# ==============================
@app.route("/api/license/verify_hwid", methods=["GET"])
def verify_hwid():
    hwid = request.args.get("hwid", "").strip()
    if not hwid:
        return jsonify(ok=False, error="Missing HWID"), 400

    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT license_key, user, status, expire FROM licenses WHERE hwid = ?", (hwid,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify(ok=False, error="HWID not registered"), 404

    key = row["license_key"]
    user = row["user"]
    status = row["status"]
    expire_str = row["expire"]

    try:
        expire_date = datetime.datetime.strptime(expire_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify(ok=False, error="Invalid expire date format"), 500

    today = datetime.date.today()
    days_left = (expire_date - today).days

    if status != "VALID":
        return jsonify(ok=False, status=status, error="License status is not VALID"), 403
    if days_left < 0:
        return jsonify(ok=False, status="EXPIRED", error="License expired"), 403

    return jsonify(ok=True,
                   status="VALID",
                   key=key,
                   user=user,
                   expire=expire_str,
                   days_left=days_left,
                   hwid=hwid)

# ==============================
# 🔐 ADMIN – BUAT LISENSI BARU
# ==============================
@app.route("/api/admin/create", methods=["POST"])
def admin_create_license():
    if not require_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    user = data.get("user", "unknown")
    days = int(data.get("days", 30))
    hwid = data.get("hwid", None)
    expire_date = (datetime.date.today() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")

    key = secrets.token_hex(6).upper()

    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        c = conn.cursor()
        c.execute("""
            INSERT INTO licenses (license_key, user, hwid, status, expire)
            VALUES (?, ?, ?, 'VALID', ?)
        """, (key, user, hwid, expire_date))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError as e:
        return jsonify({"error": "IntegrityError", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Server error", "details": str(e)}), 500

    print(f"🆕 Lisensi dibuat: key={key}, user={user}, hwid={hwid}, expire={expire_date}")

    return jsonify({
        "message": "License created successfully",
        "key": key,
        "user": user,
        "hwid": hwid,
        "expire": expire_date
    }), 201

# ==============================
# 🧩 ADMIN – REGISTER / BIND HWID
# ==============================
@app.route("/api/admin/register_hwid", methods=["POST"])
def admin_register_hwid():
    if not require_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    key = data.get("key")
    hwid = data.get("hwid")

    if not key or not hwid:
        return jsonify({"error": "Missing key or hwid"}), 400

    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT id, hwid FROM licenses WHERE license_key = ?", (key,))
    row = c.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "License key not found"}), 404

    try:
        c.execute("UPDATE licenses SET hwid = ? WHERE license_key = ?", (hwid, key))
        conn.commit()
        conn.close()
        print(f"🔗 HWID {hwid} telah diikat ke lisensi {key}")
        return jsonify({
            "message": "HWID registered successfully",
            "key": key,
            "hwid": hwid
        }), 200
    except Exception as e:
        conn.close()
        return jsonify({"error": "Server error", "details": str(e)}), 500

# ==============================
# 🧾 ADMIN – LIST LISENSI
# ==============================
@app.route("/api/admin/list", methods=["GET"])
def admin_list_licenses():
    if not require_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    status_filter = request.args.get("status")
    user_filter = request.args.get("user")

    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        sql = "SELECT license_key, user, hwid, status, expire, created_at FROM licenses"
        conditions = []
        params = []
        if status_filter:
            conditions.append("status = ?")
            params.append(status_filter)
        if user_filter:
            conditions.append("user = ?")
            params.append(user_filter)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC"

        c.execute(sql, tuple(params))
        rows = c.fetchall()
        conn.close()

        licenses = []
        for r in rows:
            licenses.append({
                "key": r["license_key"],
                "user": r["user"],
                "hwid": r["hwid"],
                "status": r["status"],
                "expire": r["expire"],
                "created_at": r["created_at"]
            })

        return jsonify({"count": len(licenses), "licenses": licenses}), 200

    except Exception as e:
        return jsonify({"error": "Server error", "details": str(e)}), 500

# ==============================
# 🚫 ADMIN – NONAKTIFKAN LISENSI
# ==============================
@app.route("/api/admin/ban", methods=["POST"])
def admin_ban_license():
    if not require_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    key = data.get("key")
    reason = data.get("reason", "No reason provided")

    if not key:
        return jsonify({"error": "Missing license key"}), 400

    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT status FROM licenses WHERE license_key = ?", (key,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "License key not found"}), 404

        c.execute("UPDATE licenses SET status = 'BANNED' WHERE license_key = ?", (key,))
        conn.commit()
        conn.close()

        print(f"⛔ Lisensi {key} dinonaktifkan. Alasan: {reason}")
        return jsonify({
            "message": "License banned successfully",
            "key": key,
            "reason": reason
        }), 200

    except Exception as e:
        return jsonify({"error": "Server error", "details": str(e)}), 500

# ==============================
# 🔁 ADMIN – RESET DATABASE
# ==============================
@app.route("/api/admin/resetdb", methods=["POST"])
def admin_reset_db():
    if not require_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        if Path(DB_NAME).exists():
            Path(DB_NAME).unlink()
            print("🧹 Database lama dihapus.")
        init_db()
        return jsonify({"message": "Database reset successfully"}), 200
    except Exception as e:
        return jsonify({"error": "Server error", "details": str(e)}), 500

# ==============================
# 🏠 HOME
# ==============================
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "🟢 MSI ADB TOOL License Server Active"})

# ==============================
# 🚀 JALANKAN SERVER
# ==============================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Server berjalan di port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
