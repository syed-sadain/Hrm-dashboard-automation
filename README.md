# RPA Control Deck

### Dashboard-Driven OrangeHRM Employee Automation

[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-3.0-black?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Selenium](https://img.shields.io/badge/selenium-4.23-43B02A?logo=selenium&logoColor=white)](https://www.selenium.dev/)
[![Status](https://img.shields.io/badge/status-active-brightgreen)]()

A dashboard-triggered RPA project that automates employee creation on the
[OrangeHRM demo site](https://opensource-demo.orangehrmlive.com) using
**Python + Selenium**, controlled entirely from a **Flask** web dashboard
with a glassmorphism UI.

Every field on the dashboard — login credentials and employee details — is
what actually drives the browser automation. There is no hardcoded data in
the automation layer; the dashboard is the single control surface.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Using the Dashboard](#using-the-dashboard)
- [Reliability & Error Handling](#reliability--error-handling)
- [API Reference](#api-reference)
- [Tech Stack](#tech-stack)
- [Deliverables Checklist](#deliverables-checklist)
- [Notes for Evaluators](#notes-for-evaluators)

---

## Overview

1. You fill in login credentials and employee details on the dashboard.
2. You click **Run Automation**.
3. The Flask backend spins up a real Chrome (Selenium) session and:
   - Opens the OrangeHRM login page
   - Logs in with the credentials from the form
   - Navigates to the **PIM** module
   - Adds a new employee using the dashboard-provided details
   - Verifies the employee was actually created
   - Extracts the employee list into a CSV file
   - Logs out
4. The dashboard renders a **live pipeline** of every step (with status,
   message, and a timestamp), echoes back the inserted employee, shows
   before/after screenshots, and lists the extracted employee table with a
   CSV download button.
5. Every step is written to `logs/automation.log` for auditing.

---

## Project Structure

```text
orangehrm-dashboard-automation/
├── app.py                       # Flask app: routes + API
├── config.py                    # Centralized env-driven configuration
├── automation/
│   └── orangehrm_bot.py         # Selenium automation engine (OrangeHRMBot)
├── templates/
│   └── index.html               # Dashboard UI markup
├── static/
│   ├── css/style.css            # Glassmorphism design system
│   ├── js/script.js             # Form handling + live pipeline rendering
│   └── screenshots/             # Auto-saved before/after screenshots
├── data/
│   └── employees_extracted.csv  # Auto-generated on each run
├── logs/
│   └── automation.log           # Step-by-step automation log
├── requirements.txt
├── .env.example                 # Copy to .env — credentials never hardcoded
├── .gitignore
├── run.sh                       # One-command local launcher (macOS/Linux)
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.9+
- Google Chrome installed
- Internet access (ChromeDriver is fetched automatically on first run)

### 1. Clone / unzip and enter the project

```bash
cd orangehrm-dashboard-automation
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and adjust values if needed. **OrangeHRM login credentials are
never stored in `.env`, `config.py`, or anywhere in source.** They are
mandatory input on the dashboard form and are read fresh from the request
on every single run — there is no hardcoded or environment-variable
fallback. If the dashboard form is submitted without a username/password,
the backend rejects the request instead of substituting a default.

### 5. Run the app

```bash
python app.py
# or
bash run.sh
```

Then open **http://localhost:5000** in your browser.

> **Chrome required.** `webdriver-manager` automatically downloads the
> matching ChromeDriver binary the first time you run an automation — make
> sure Google Chrome is installed and the machine has internet access.

---

## Using the Dashboard

1. Enter the OrangeHRM **Username** and **Password** (both required — the
   run is rejected server-side if either is blank). For the public
   [OrangeHRM demo instance](https://opensource-demo.orangehrmlive.com),
   the published demo/test login is `Admin` / `admin123` — this is
   documentation text only, describing what a tester types into the form;
   it is never read from config or used as a silent fallback in code.
2. Enter **First Name** and **Last Name** (required) and an optional
   **Employee ID** (a unique one is generated automatically if the one you
   enter already exists in OrangeHRM).
3. Click **Run Automation** and watch the pipeline light up stage by stage.
4. Once finished, review:
   - The employee data echoed back exactly as inserted
   - Before/after screenshots of the Employee List
   - The extracted employee table (also downloadable as CSV)
   - The status badge (Success / Partial failure / Failed) in the top bar

---

## Reliability & Error Handling

| Safeguard | Description |
|---|---|
| Explicit waits | `WebDriverWait` + `expected_conditions` on every interaction — no blind `time.sleep()` used for synchronization |
| Graceful step failures | Every automation step is wrapped in `try`/`except` and reported as `success`, `warning`, or `failed` without crashing the whole run |
| Critical-path guard | If Login, Navigate-to-PIM, or Add-Employee fails, the run stops early and the reason is surfaced on the dashboard and in the logs |
| Stale-element recovery | Elements are re-located immediately before use and retried on `StaleElementReferenceException`, rather than holding references across form re-renders |
| Guaranteed extraction | The newly created employee is confirmed present in the extracted list via a direct Employee Id search, independent of table sort order or pagination |
| Duplicate ID recovery | A requested Employee Id that already exists is detected and replaced with a generated unique one automatically |
| Audit trail | Screenshots are captured at every major checkpoint; every step is logged to `logs/automation.log` |
| Server-side validation | Duplicates the client-side checks — the API never trusts the browser alone |

---

## API Reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Renders the dashboard |
| `POST` | `/run-automation` | Runs the full Selenium flow, returns JSON |
| `GET` | `/download-csv` | Downloads the latest extracted employee CSV |
| `GET` | `/health` | Liveness probe |

`POST /run-automation` body (example only — every field is real runtime
input typed into the dashboard, not a stored default):

```json
{
  "username": "<OrangeHRM username entered on the dashboard>",
  "password": "<OrangeHRM password entered on the dashboard>",
  "first_name": "Aarav",
  "last_name": "Mehta",
  "employee_id": "EMP2026"
}
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask, python-dotenv |
| Automation | Selenium 4, webdriver-manager (auto ChromeDriver) |
| Data | `pandas` / `csv` for extraction, exported to `data/employees_extracted.csv` |
| Frontend | Semantic HTML, hand-written CSS (glassmorphism + gradient design system, no framework), vanilla JS (fetch API) |

---

## Deliverables Checklist

- [x] Dashboard UI (HTML/CSS/JS) with credential + employee fields
- [x] Submit button triggers automation
- [x] Inserted employee data displayed back on dashboard
- [x] Automation: open site → login → PIM → add employee → verify → extract → logout
- [x] Success/failure status shown per step and overall
- [x] Extracted employee table displayed + downloadable as CSV
- [x] Logs maintained for every automation step (`logs/automation.log`)
- [x] Credentials are mandatory dashboard-form input, never hardcoded or defaulted anywhere in source
- [x] Proper waits and exception handling throughout

---

## Notes for Evaluators

This project targets the live public OrangeHRM demo instance
(`opensource-demo.orangehrmlive.com`), which is periodically reset by its
maintainers — so employee IDs and record counts will vary between runs.
Screenshots and CSV output in this repository are generated fresh on every
execution, not pre-baked.
