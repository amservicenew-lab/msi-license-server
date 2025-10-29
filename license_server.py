from flask import Flask, request, jsonify
import sqlite3
import datetime
import os
import secrets

app = Flask(__name__)

# ==============================
# ⚙️ KONFIGURASI
# ==============================
DB_NAME = "licenses.db"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "super-long-admin-token-xyz")  # Ganti di Render ENV

# ==============================
# 🧱 INISIALISASI DATABASE
# ==============================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            user TEXT,
            hwid TEXT,
            status TEXT NOT NULL DEFAULT 'VALID',
            expire TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Database siap digunakan.")


# ==============================
# 🛡️ ADMIN TOKEN VALIDATOR
# ==============================
def require_admin(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token = auth.split("Bearer ")[1].strip()
    return token == ADMIN_TOKEN


# ==============================
# 🔍 CEK LISENSI
# ==============================
@app.route("/api/license", methods=["GET"])
def check_license():
    key = request.args.get("key")
    hwid = request.args.get("hwid")

    if not key:
        return jsonify({"status": "MISSING_KEY"}), 400

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT status, expire, hwid FROM licenses WHERE license_key = ?", (key,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "INVALID"}), 404

    status, expire, stored_hwid = row

    # 🧩 1️⃣ Jika lisensi belum punya HWID, simpan HWID baru (binding)
    if status == "VALID" and (stored_hwid is None or stored_hwid.strip() == "") and hwid:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("UPDATE licenses SET hwid = ? WHERE license_key = ?", (hwid, key))
        conn.commit()
        conn.close()
        stored_hwid = hwid
        print(f"🔗 Lisensi {key} diikat ke HWID {hwid}")

    # 🧩 2️⃣ Jika lisensi sudah punya HWID tapi tidak cocok, tolak
    if stored_hwid and hwid and hwid.strip().upper() != stored_hwid.strip().upper():
        return jsonify({"status": "HWID_MISMATCH"}), 403

    # 🧩 3️⃣ Cek status lisensi
    if status != "VALID":
        return jsonify({"status": status}), 403

    # 🧩 4️⃣ Cek masa berlaku
    expire_date = datetime.datetime.strptime(expire, "%Y-%m-%d").date()
    today = datetime.date.today()
    days_left = (expire_date - today).days
    if days_left < 0:
        return jsonify({"status": "EXPIRED"}), 403

    # 🧩 5️⃣ Balikan hasil sukses
    return jsonify({
        "status": "VALID",
        "expire": expire,
        "days_left": days_left,
        "hwid": stored_hwid
    })

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT status, expire, hwid FROM licenses WHERE license_key = ?", (key,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "INVALID"}), 404

    status, expire, hwid = row
    if status != "VALID":
        return jsonify({"status": status}), 403

    expire_date = datetime.datetime.strptime(expire, "%Y-%m-%d").date()
    today = datetime.date.today()
    days_left = (expire_date - today).days
    if days_left < 0:
        return jsonify({"status": "EXPIRED"}), 403

    return jsonify({
        "status": "VALID",
        "expire": expire,
        "days_left": days_left,
        "hwid": hwid
    })


# ==============================
# 🔐 ADMIN: BUAT LISENSI BARU
# ==============================
@app.route("/api/admin/create", methods=["POST"])
def admin_create_license():
    if not require_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.get_json()
        user = data.get("user", "unknown")
        days = int(data.get("days", 30))
        hwid = data.get("hwid")
        expire_date = (datetime.date.today() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")

        # Generate random license key
        key = secrets.token_hex(6).upper()

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("""
            INSERT INTO licenses (license_key, user, hwid, status, expire)
            VALUES (?, ?, ?, 'VALID', ?)
        """, (key, user, hwid, expire_date))
        conn.commit()
        conn.close()

        print(f"🆕 Lisensi dibuat untuk user '{user}' (key: {key})")

        return jsonify({
            "message": "License created successfully",
            "key": key,
            "user": user,
            "expire": expire_date
        }), 201

    except Exception as e:
        print("🔥 ERROR saat membuat lisensi:", e)
        return jsonify({"error": str(e)}), 500

# ==============================
# 🧾 ADMIN: LIST ALL LICENSES
# ==============================
@app.route("/api/admin/list", methods=["GET"])
def admin_list_licenses():
    if not require_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    # optional query params: status, user
    status_filter = request.args.get("status")
    user_filter = request.args.get("user")

    try:
        conn = sqlite3.connect(DB_NAME)
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
        print("ERROR listing licenses:", e)
        return jsonify({"error": str(e)}), 500
        
# ==============================
# 🚫 ADMIN: NONAKTIFKAN / BAN LISENSI
# ==============================
@app.route("/api/admin/ban", methods=["POST"])
def admin_ban_license():
    if not require_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    key = data.get("key") or request.args.get("key")
    reason = data.get("reason", "No reason provided")

    if not key:
        return jsonify({"error": "Missing license key"}), 400

    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        # cek apakah lisensi ada
        c.execute("SELECT status FROM licenses WHERE license_key = ?", (key,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "License key not found"}), 404

        # update status jadi BANNED
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
        print("🔥 ERROR saat ban license:", e)
        return jsonify({"error": str(e)}), 500

# ==============================
# 🧨 ADMIN: RESET DATABASE
# ==============================
@app.route("/api/admin/resetdb", methods=["POST"])
def reset_database():
    if not require_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)
            print("🧹 Database lama dihapus.")

        init_db()
        print("✅ Database baru dibuat.")
        return jsonify({"message": "Database reset successfully"}), 200

    except Exception as e:
        print("🔥 ERROR saat reset database:", e)
        return jsonify({"error": str(e)}), 500


# ==============================
# 🏠 HOME ENDPOINT
# ==============================
@app.route("/")
def home():
    return jsonify({"message": "🟢 MSI ADB TOOL License Server Active"})


# ==============================
# 🚀 JALANKAN SERVER
# ==============================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Server berjalan di port {port}")
    app.run(host="0.0.0.0", port=port)
