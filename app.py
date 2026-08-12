"""
Flask backend for the Dashboard-Driven OrangeHRM Automation project.

Routes
------
GET  /                -> renders the dashboard UI
POST /run-automation  -> triggers the Selenium flow using dashboard inputs,
                          returns structured JSON (timeline, employee, CSV path)
GET  /download-csv    -> serves the most recently extracted employee CSV
GET  /health          -> simple liveness probe
"""
import logging
import os

from flask import Flask, jsonify, render_template, request, send_from_directory

from automation.orangehrm_bot import AutomationError, OrangeHRMBot
from config import Config

# --------------------------------------------------------------------------- #
# App + logging setup
# --------------------------------------------------------------------------- #
os.makedirs(Config.LOG_DIR, exist_ok=True)
os.makedirs(Config.SCREENSHOT_DIR, exist_ok=True)
os.makedirs(Config.DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("app")

app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run-automation", methods=["POST"])
def run_automation():
    payload = request.get_json(silent=True) or {}

    # Credentials are mandatory runtime input from the dashboard form.
    # There is no fallback to a hardcoded or environment-configured value:
    # if the dashboard didn't send them, the run does not proceed.
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()
    first_name = (payload.get("first_name") or "").strip()
    last_name = (payload.get("last_name") or "").strip()
    employee_id = (payload.get("employee_id") or "").strip()

    # --- Server-side validation (never trust the client alone) ---
    errors = []
    if not username:
        errors.append("Username is required.")
    if not password:
        errors.append("Password is required.")
    if not first_name:
        errors.append("First name is required.")
    if not last_name:
        errors.append("Last name is required.")
    if employee_id and len(employee_id) > 10:
        errors.append("Employee ID must be 10 characters or fewer (OrangeHRM field limit).")
    if errors:
        logger.warning("Validation failed for /run-automation: %s", errors)
        return jsonify({"overall_status": "validation_error", "errors": errors}), 400

    logger.info(
        "Automation triggered from dashboard for employee '%s %s' (id=%s)",
        first_name, last_name, employee_id or "auto",
    )

    bot = OrangeHRMBot()
    try:
        result = bot.run_full_flow(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            employee_id=employee_id or None,
        )
        result["employee"] = result.get("inserted_employee")
        result["csv_path"] = result.get("csv_file")
        # NOTE: the HTTP status code is informational only. The dashboard and
        # any consumer of this API must key success/failure off the
        # "overall_status" field in the JSON body, never off the status code
        # alone (a 200 here does not by itself mean every step succeeded).
        status_code = {"success": 200, "partial_failure": 207, "failed": 422}.get(result["overall_status"], 207)
        return jsonify(result), status_code
    except AutomationError as exc:
        logger.exception("Unhandled automation error")
        return jsonify({"overall_status": "failed", "error": str(exc), "timeline": bot.timeline}), 500
    except Exception as exc:  # last-resort safety net, always logged
        logger.exception("Unexpected server error during automation run")
        return jsonify({"overall_status": "failed", "error": f"Unexpected server error: {exc}"}), 500


@app.route("/download-csv")
def download_csv():
    if not os.path.exists(Config.CSV_FILE):
        return jsonify({"error": "No extracted data available yet. Run the automation first."}), 404
    return send_from_directory(Config.DATA_DIR, "employees_extracted.csv", as_attachment=True)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=Config.DEBUG, port=Config.PORT)
