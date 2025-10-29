from flask import Flask, request, jsonify
import sqlite3
import datetime
import os

app = Flask(__name__)

DB_NAME = "licenses.db"

# ------------------------------
# 🧱 Inisialisasi Database
# ------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'VALID',
            expire TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# ------------------------------
# 🔍 Cek License
# ------------------------------
@app.route("/api/license", methods=["GET"])
def check_license():
    key = request.args.get("key")
    hwid = request.args.get("hwid")

    if not key:
        return jsonify({"status": "MISSING_KEY"}), 400

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT status, expire FROM licenses WHERE license_key = ?", (key,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "INVALID"}), 404

    status, expire = row
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
        "days_left": days_left
    })


# ------------------------------
# ➕ Tambah License (POST)
# ------------------------------
@app.route("/api/license/add", methods=["POST"])
def add_license():
    data = request.get_json()
    key = data.get("key")
    expire = data.get("expire")
    status = data.get("status", "VALID")

    if not key or not expire:
        return jsonify({"error": "Missing key or expire"}), 400

    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO licenses (license_key, status, expire) VALUES (?, ?, ?)", (key, status, expire))
        conn.commit()
        conn.close()
        return jsonify({"message": "License added successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "License key already exists"}), 409


# ------------------------------
# ❌ Hapus License (DELETE)
# ------------------------------
@app.route("/api/license/delete", methods=["DELETE"])
def delete_license():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "Missing key"}), 400

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM licenses WHERE license_key = ?", (key,))
    conn.commit()
    conn.close()

    return jsonify({"message": f"License {key} deleted (if it existed)."})


# ------------------------------
# 🏠 Root Endpoint
# ------------------------------
@app.route("/")
def home():
    return jsonify({"message": "🟢 MSI ADB TOOL License Server Active"})


# ------------------------------
# 🚀 Run Server
# ------------------------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
