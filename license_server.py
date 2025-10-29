
from flask import Flask, request, jsonify
import datetime

app = Flask(__name__)

licenses = {
    "ABC123": {"status": "VALID", "expire": "2025-12-31"},
    "TRIAL001": {"status": "VALID", "expire": "2025-11-15"},
    "XYZ789": {"status": "BANNED", "expire": "2025-10-01"}
}

@app.route("/api/license", methods=["GET"])
def check_license():
    key = request.args.get("key")
    hwid = request.args.get("hwid")

    if not key:
        return jsonify({"status": "MISSING_KEY"}), 400

    info = licenses.get(key)
    if not info:
        return jsonify({"status": "INVALID"}), 404

    if info["status"] != "VALID":
        return jsonify({"status": info["status"]}), 403

    expire_date = datetime.datetime.strptime(info["expire"], "%Y-%m-%d").date()
    today = datetime.date.today()
    days_left = (expire_date - today).days
    if days_left < 0:
        return jsonify({"status": "EXPIRED"}), 403

    return jsonify({
        "status": "VALID",
        "expire": info["expire"],
        "days_left": days_left
    })

@app.route("/")
def home():
    return jsonify({"message": "MSI ADB TOOL License Server Active ✅"})

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

