"""
Centralized configuration loaded from environment variables (.env).
Keeping every tunable value here means no credential or magic string
is ever hardcoded inside the automation or Flask layers.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- Target application ---
    ORANGEHRM_URL = os.getenv(
        "ORANGEHRM_URL",
        "https://opensource-demo.orangehrmlive.com/web/index.php/auth/login",
    )

    # NOTE: OrangeHRM login credentials are NOT configured here. They are
    # mandatory runtime input supplied by the dashboard form on every run
    # and are never given a hardcoded or environment-variable fallback.

    # --- Flask ---
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
    DEBUG = os.getenv("FLASK_DEBUG", "True") == "True"
    PORT = int(os.getenv("FLASK_PORT", 5000))

    # --- Selenium ---
    RUN_HEADLESS = os.getenv("RUN_HEADLESS", "True") == "True"
    IMPLICIT_WAIT = int(os.getenv("IMPLICIT_WAIT_SECONDS", 10))
    EXPLICIT_WAIT = int(os.getenv("EXPLICIT_WAIT_SECONDS", 15))

    # --- Paths ---
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SCREENSHOT_DIR = os.path.join(BASE_DIR, "static", "screenshots")
    DATA_DIR = os.path.join(BASE_DIR, "data")
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    LOG_FILE = os.path.join(LOG_DIR, "automation.log")
    CSV_FILE = os.path.join(DATA_DIR, "employees_extracted.csv")
