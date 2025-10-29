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
    if not key:
        return jsonify({"status": "MISSING_KEY"}), 400

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
