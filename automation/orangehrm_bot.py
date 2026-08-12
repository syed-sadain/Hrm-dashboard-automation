"""
OrangeHRM Selenium automation engine.

Design notes
------------
* Every public step returns a small dict: {"step", "status", "message", "screenshot"}
  so the Flask layer can stream a clean, structured timeline back to the dashboard.
* All waits are EXPLICIT (WebDriverWait + expected_conditions) — no time.sleep()
  used for synchronization, only as a last-resort micro-delay after an action
  that is known to trigger a client-side animation.
* Every browser interaction is wrapped in try/except so a single failed step
  degrades gracefully instead of crashing the whole run, and is logged with
  full context to logs/automation.log.
* Credentials are never hardcoded here — they are passed in from the caller,
  which in turn sources them from the dashboard form or config.py/.env.
"""
import csv
import logging
import os
import time
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import Config

logger = logging.getLogger("orangehrm_automation")


class AutomationError(Exception):
    """Raised when a critical automation step cannot recover."""


class OrangeHRMBot:
    def __init__(self, base_url: str = None, headless: bool = None):
        self.base_url = base_url or Config.ORANGEHRM_URL
        self.headless = Config.RUN_HEADLESS if headless is None else headless
        self.driver = None
        self.wait = None
        self.timeline = []  # ordered list of step results for the dashboard
        self.last_employee_id = None  # actual employee id used/assigned this run

    # ------------------------------------------------------------------ #
    # Driver lifecycle
    # ------------------------------------------------------------------ #
    def start_driver(self):
        try:
            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--window-size=1440,900")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-notifications")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.implicitly_wait(Config.IMPLICIT_WAIT)
            self.wait = WebDriverWait(self.driver, Config.EXPLICIT_WAIT)
            logger.info("Chrome WebDriver started (headless=%s)", self.headless)
        except WebDriverException as exc:
            logger.exception("Failed to start WebDriver")
            raise AutomationError(f"Could not start browser driver: {exc}") from exc

    def quit_driver(self):
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver session closed")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _screenshot(self, label: str) -> str:
        """Save a timestamped screenshot and return its web-relative path."""
        os.makedirs(Config.SCREENSHOT_DIR, exist_ok=True)
        filename = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(Config.SCREENSHOT_DIR, filename)
        try:
            self.driver.save_screenshot(filepath)
            logger.info("Screenshot captured: %s", filename)
            return f"screenshots/{filename}"
        except WebDriverException:
            logger.warning("Screenshot capture failed for label=%s", label)
            return ""

    def _save_named_screenshot(self, filename: str) -> str:
        """Save a screenshot under a fixed filename (overwritten each run).

        Distinct from _screenshot(): this is used for the dashboard's
        Before/After widget (before_state.png / after_state.png), which
        needs a stable, predictable path rather than a new timestamped file
        per run. Raises on failure so the caller decides the fallback.
        """
        os.makedirs(Config.SCREENSHOT_DIR, exist_ok=True)
        filepath = os.path.join(Config.SCREENSHOT_DIR, filename)
        self.driver.save_screenshot(filepath)
        return f"screenshots/{filename}"

    def capture_before_state(self):
        """Capture the PIM Employee List page BEFORE the new employee is
        added, for the dashboard's Before/After widget. Never raises: on
        any failure it logs a warning and returns None so the dashboard can
        fall back to a placeholder instead of crashing.
        """
        try:
            base_url = self.base_url.replace("/auth/login", "")
            self.driver.get(f"{base_url}/pim/viewEmployeeList")
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-body")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-card")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-filter")),
                )
            )
            self.wait_for_form_to_be_ready(25)
            path = self._save_named_screenshot("before_state.png")
            logger.info("Screenshot captured: before_state.png")
            return path
        except (TimeoutException, NoSuchElementException, WebDriverException) as exc:
            logger.warning(
                "Could not capture before_state.png (%s: %s); dashboard will fall back to a placeholder.",
                type(exc).__name__, exc,
            )
            return None

    def capture_after_state(self):
        """Capture the PIM Employee List page AFTER the new employee was
        added (refreshed, so the new row is guaranteed to be reflected), for
        the dashboard's Before/After widget. Never raises: on any failure it
        logs a warning and returns None so the dashboard can fall back to a
        placeholder instead of crashing.
        """
        try:
            base_url = self.base_url.replace("/auth/login", "")
            self.driver.get(f"{base_url}/pim/viewEmployeeList")
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-body")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-card")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-filter")),
                )
            )
            self.wait_for_form_to_be_ready(25)
            self.driver.refresh()
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-body")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-card")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-filter")),
                )
            )
            self.wait_for_form_to_be_ready(25)
            path = self._save_named_screenshot("after_state.png")
            logger.info("Screenshot captured: after_state.png")
            return path
        except (TimeoutException, NoSuchElementException, WebDriverException) as exc:
            logger.warning(
                "Could not capture after_state.png (%s: %s); dashboard will fall back to a placeholder.",
                type(exc).__name__, exc,
            )
            return None

    def _record(self, step: str, status: str, message: str, screenshot: str = ""):
        entry = {
            "step": step,
            "status": status,  # "success" | "failed" | "warning"
            "message": message,
            "screenshot": screenshot,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        self.timeline.append(entry)
        log_fn = logger.info if status == "success" else logger.error
        log_fn("[%s] %s - %s", step, status.upper(), message)
        return entry

    def wait_for_form_to_be_ready(self, timeout: int = 25):
        """Wait for OrangeHRM's loading overlay/spinner (the element that causes
        ElementClickInterceptedException on the Save button) to fully disappear
        before any further interaction. Uses its own WebDriverWait so the caller
        can request a longer timeout than the default explicit wait."""
        local_wait = WebDriverWait(self.driver, timeout)
        overlay_selector = ".oxd-form-loader, .oxd-loading-spinner, .oxd-loading-spinner-container"
        try:
            local_wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
            local_wait.until(
                lambda driver: all(not el.is_displayed() for el in driver.find_elements(By.CSS_SELECTOR, overlay_selector))
            )
        except TimeoutException:
            logger.warning("OrangeHRM loader/overlay did not disappear within %ss; forcing it off defensively.", timeout)
            self.driver.execute_script(
                """
                document.querySelectorAll(arguments[0]).forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    el.style.opacity = '0';
                    el.style.pointerEvents = 'none';
                });
                """,
                overlay_selector,
            )
            time.sleep(0.5)

    def _set_field_value(self, element, value: str) -> str:
        """Reliably replace an OXD/Vue-controlled input's value.

        Selenium's element.clear() does NOT reset these inputs: the DOM value
        attribute is left untouched, so a subsequent send_keys() *appends* to
        the old text instead of replacing it (confirmed by inspecting the
        Employee Id field, which is pre-filled with a system-assigned value).
        That silently corrupts submitted data and was a real cause of Save
        failures (e.g. "Should not exceed 10 characters" on a field that only
        looked empty). Select-all + Delete clears the underlying Vue model
        correctly; a JS fallback re-verifies as a last resort.
        """
        element.click()
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(Keys.DELETE)
        if element.get_attribute("value"):
            self.driver.execute_script(
                "arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
                element,
            )
        if value:
            element.send_keys(value)
        actual = element.get_attribute("value")
        if actual != (value or ""):
            self.driver.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                element, value or "",
            )
            actual = element.get_attribute("value")
        return actual

    def _find_employee_id_field(self):
        try:
            return self.driver.find_element(
                By.XPATH,
                "//label[normalize-space()='Employee Id']/ancestor::div[contains(@class, 'oxd-input-group')]//input",
            )
        except NoSuchElementException:
            try:
                return self.driver.find_element(By.NAME, "employeeId")
            except NoSuchElementException:
                return None

    def _field_error_message(self, element):
        """Return the OXD inline validation error text for a field's input group, if any."""
        if element is None:
            return None
        try:
            group = element.find_element(By.XPATH, "./ancestor::div[contains(@class, 'oxd-input-group')]")
            for err in group.find_elements(By.CSS_SELECTOR, ".oxd-input-field-error-message"):
                text = err.text.strip()
                if text:
                    return text
        except (NoSuchElementException, StaleElementReferenceException):
            pass
        return None

    @staticmethod
    def _generate_unique_employee_id() -> str:
        """EMP id derived from a millisecond timestamp, kept <=10 chars to satisfy
        OrangeHRM's Employee Id field length constraint."""
        return "E" + str(int(time.time() * 1000))[-9:]

    def _stale_safe(self, locate_fn, action_fn, retries: int = 3, delay: float = 0.3):
        """Run action_fn(element) where element = locate_fn(), retrying by
        re-locating on StaleElementReferenceException.

        OrangeHRM's Add Employee form is a Vue component: typing into one
        field (e.g. Employee Id) can trigger the form to re-render, which
        replaces the underlying DOM nodes for OTHER fields too. Any
        previously-fetched WebElement reference for those fields then
        becomes stale on its next use, even though nothing about the
        field's role or content actually changed. Always re-locating
        immediately before use (instead of holding a reference across other
        interactions) is what actually fixes this, rather than a blind
        retry of the same action.
        """
        last_exc = None
        for attempt in range(retries):
            try:
                element = locate_fn()
                return action_fn(element)
            except StaleElementReferenceException as exc:
                last_exc = exc
                logger.warning(
                    "Stale element reference (attempt %s/%s); re-locating and retrying: %s",
                    attempt + 1, retries, exc,
                )
                time.sleep(delay)
        raise last_exc

    def click_element_safely(self, element):
        """Click an element while handling OrangeHRM loader overlays and stale references."""
        if element is None:
            return False
        for attempt in range(4):
            try:
                self.wait.until(EC.element_to_be_clickable(element))
                element.click()
                return True
            except (ElementClickInterceptedException, StaleElementReferenceException):
                self.wait_for_form_to_be_ready()
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception:
                    pass
            except WebDriverException:
                self.wait_for_form_to_be_ready()
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", element)
                return True
            except Exception:
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception:
                    pass
        return False

    # ------------------------------------------------------------------ #
    # Automation steps
    # ------------------------------------------------------------------ #
    def open_site(self):
        step = "Open OrangeHRM"
        try:
            self.driver.get(self.base_url)
            self.wait.until(EC.presence_of_element_located((By.NAME, "username")))
            logger.info("OrangeHRM opened: %s", self.base_url)
            shot = self._screenshot("01_login_page")
            return self._record(step, "success", "Login page loaded successfully.", shot)
        except TimeoutException:
            shot = self._screenshot("01_login_page_error")
            return self._record(step, "failed", "Login page did not load in time.", shot)

    def login(self, username: str, password: str):
        step = "Login"
        shot = ""
        try:
            logger.info("Login started for user '%s'.", username)
            user_field = self.wait.until(EC.presence_of_element_located((By.NAME, "username")))
            pass_field = self.driver.find_element(By.NAME, "password")
            self._set_field_value(user_field, username)
            self._set_field_value(pass_field, password)
            self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

            # Success = dashboard header appears; failure = alert error message appears
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-topbar-header-breadcrumb")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-alert-content-text")),
                )
            )

            if self.driver.find_elements(By.CLASS_NAME, "oxd-alert-content-text"):
                error_text = self.driver.find_element(By.CLASS_NAME, "oxd-alert-content-text").text
                shot = self._screenshot("02_login_failed")
                raise AutomationError(f"Login rejected by application: {error_text}")

            logger.info("Login successful for user '%s'.", username)
            shot = self._screenshot("02_login_success")
            return self._record(step, "success", f"Logged in as '{username}'.", shot)
        except TimeoutException:
            shot = self._screenshot("02_login_timeout")
            return self._record(step, "failed", "Timed out waiting for dashboard after login.", shot)
        except AutomationError as exc:
            return self._record(step, "failed", str(exc), shot)

    def navigate_to_pim(self):
        step = "Navigate to PIM"
        try:
            logger.info("PIM navigation started.")
            base_url = self.base_url.replace("/auth/login", "")
            self.driver.get(f"{base_url}/pim/viewEmployeeList")
            self.wait.until(
                EC.any_of(
                    EC.url_contains("/pim/viewEmployeeList"),
                    EC.presence_of_element_located((By.XPATH, "//h5[text()='Employee Information']")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-filter-title")),
                )
            )
            shot = self._screenshot("03_pim_module")
            return self._record(step, "success", "PIM module opened.", shot)
        except (TimeoutException, NoSuchElementException, WebDriverException) as exc:
            shot = self._screenshot("03_pim_error")
            return self._record(step, "failed", f"Could not open the PIM module: {exc}", shot)

    def add_employee(self, first_name: str, last_name: str, employee_id: str = None):
        step = "Add Employee"
        self.last_employee_id = employee_id
        try:
            logger.info("Add Employee started for '%s %s' (requested id=%s)", first_name, last_name, employee_id or "system-assigned")

            base_url = self.base_url.replace("/auth/login", "")
            self.driver.get(f"{base_url}/pim/addEmployee")

            # 1. Wait for the Add Employee page/form to actually be loaded and visible.
            self.wait.until(EC.presence_of_element_located((By.NAME, "firstName")))
            self.wait.until(EC.visibility_of_element_located((By.NAME, "firstName")))
            # 2. Wait for any loading spinner/overlay to disappear before touching the form.
            self.wait_for_form_to_be_ready(25)

            # 3. Locate fields, clear them reliably, and enter dashboard-provided
            # values. Each field is re-located immediately before it is used
            # (never held across another field's interaction) and wrapped in
            # _stale_safe(), because typing into the Employee Id field can
            # cause OrangeHRM's Vue form to re-render First/Last Name's DOM
            # nodes out from under an earlier reference.
            first_locator = lambda: self.driver.find_element(By.NAME, "firstName")
            last_locator = lambda: self.driver.find_element(By.NAME, "lastName")

            self._stale_safe(first_locator, lambda el: self._set_field_value(el, first_name))
            self._stale_safe(last_locator, lambda el: self._set_field_value(el, last_name))

            id_field = self._find_employee_id_field()
            if id_field is not None:
                system_assigned_id = self._stale_safe(self._find_employee_id_field, lambda el: el.get_attribute("value"))
            else:
                system_assigned_id = None

            if employee_id and id_field is not None:
                self._stale_safe(self._find_employee_id_field, lambda el: self._set_field_value(el, employee_id))
                self.last_employee_id = employee_id
            else:
                # No id supplied by the dashboard: OrangeHRM auto-fills the next
                # available id. Capture the real value so it can be reported
                # back to the dashboard instead of a vague placeholder.
                self.last_employee_id = system_assigned_id

            # 4. Verify the entered values before clicking Save (re-located
            # fresh, not the references captured above, for the same reason).
            actual_first = self._stale_safe(first_locator, lambda el: el.get_attribute("value"))
            actual_last = self._stale_safe(last_locator, lambda el: el.get_attribute("value"))
            if actual_first != first_name or actual_last != last_name:
                raise AutomationError(
                    f"Field verification failed before save: expected '{first_name}/{last_name}', "
                    f"found '{actual_first}/{actual_last}'."
                )
            logger.info(
                "Employee data entered: first='%s' last='%s' id='%s' (verified against form fields)",
                actual_first, actual_last, self.last_employee_id or "system-assigned",
            )

            # 5. Wait for overlays again (they can reappear after typing/validation).
            self.wait_for_form_to_be_ready(25)

            # 6-11. Locate Save, verify visible/enabled/clickable, click, and
            # transparently recover if OrangeHRM rejects the requested Employee Id
            # as a duplicate (a real, common failure mode on the shared demo
            # instance) by generating a fresh unique id and resubmitting — this is
            # state-driven recovery, not a blind retry of the same click.
            def _locate_save_button():
                return self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Save']"))
                )

            def _prepare_and_click_save(btn):
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                if not btn.is_displayed():
                    raise ElementClickInterceptedException("Save button located but not visible.")
                if not btn.is_enabled():
                    raise ElementClickInterceptedException("Save button located but not enabled.")
                logger.info("Save button ready (visible, enabled, clickable).")
                if not self.click_element_safely(btn):
                    raise ElementClickInterceptedException("Save button could not be clicked safely (still covered by loader overlay).")

            for id_attempt in range(3):
                # Re-locates the button fresh if it goes stale between being
                # found and being scrolled/checked/clicked.
                self._stale_safe(_locate_save_button, _prepare_and_click_save)

                # Wait for any post-click overlay/spinner to clear before inspecting the result.
                self.wait_for_form_to_be_ready(25)

                if employee_id:
                    error_msg = self._stale_safe(self._find_employee_id_field, self._field_error_message)
                    if error_msg and "already exists" in error_msg.lower():
                        new_id = self._generate_unique_employee_id()
                        logger.warning(
                            "Employee Id '%s' already exists in OrangeHRM; generating unique id '%s' and resubmitting.",
                            self.last_employee_id, new_id,
                        )
                        self._stale_safe(self._find_employee_id_field, lambda el: self._set_field_value(el, new_id))
                        self.last_employee_id = new_id
                        continue  # resubmit with the regenerated id

                break

            # 12. Wait for the save operation to finish and the page to transition.
            if not self._wait_for_personal_details_page(first_name, last_name, timeout=45):
                raise TimeoutException("OrangeHRM did not redirect to the employee details page after Save.")

            logger.info("Employee saved: OrangeHRM redirected to the Personal Details page.")
            shot = self._screenshot("04_employee_added")
            return self._record(
                step, "success",
                f"Employee '{first_name} {last_name}' created with id '{self.last_employee_id or 'system-assigned'}'.",
                shot,
            )
        except (TimeoutException, NoSuchElementException, ElementClickInterceptedException, WebDriverException, AutomationError) as exc:
            logger.error("Add Employee failed: %s: %s", type(exc).__name__, exc)
            shot = self._screenshot("04_employee_add_error")
            return self._record(step, "failed", f"Employee creation failed: {type(exc).__name__}: {exc}", shot)

    def _wait_for_personal_details_page(self, first_name: str, last_name: str, timeout: int = 45):
        """Poll the page until the OrangeHRM Employee Details screen is actually visible."""
        deadline = time.time() + timeout
        full_name = f"{first_name} {last_name}".lower()
        while time.time() < deadline:
            try:
                current_url = self.driver.current_url.lower()
                if "/pim/viewpersonaldetails" in current_url:
                    page_text = (self.driver.find_element(By.TAG_NAME, "body").text or "").lower()
                    if "personal details" in page_text or full_name in page_text:
                        return True

                page_text = (self.driver.find_element(By.TAG_NAME, "body").text or "").lower()
                if "personal details" in page_text and (full_name in page_text or self.driver.find_elements(By.XPATH, "//h6[normalize-space()='Personal Details']")):
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def verify_employee_created(self, first_name: str, last_name: str, employee_id: str = None):
        """Confirm employee creation using multiple independent checks:
        URL transition, name on the Personal Details page, and (where
        available) the Employee Id field actually holding the expected id."""
        step = "Verify Creation"
        try:
            if not self._wait_for_personal_details_page(first_name, last_name, timeout=45):
                raise TimeoutException("OrangeHRM personal details page did not appear after save.")

            url_confirmed = "viewpersonaldetails" in self.driver.current_url.lower()

            candidate_text = (self.driver.find_element(By.TAG_NAME, "body").text or "").lower()
            full_name = f"{first_name} {last_name}".lower()
            name_confirmed = full_name in candidate_text or any(
                full_name in h.text.lower() for h in self.driver.find_elements(By.XPATH, "//h6")
            )

            id_confirmed = None
            actual_id = None
            if employee_id:
                id_field = self._find_employee_id_field()
                actual_id = id_field.get_attribute("value") if id_field is not None else None
                id_confirmed = actual_id == employee_id

            if url_confirmed and name_confirmed and id_confirmed is not False:
                detail = f"Employee '{first_name} {last_name}' confirmed on Personal Details page (URL + name checks passed)."
                if employee_id:
                    detail += f" Employee Id confirmed as '{actual_id}'." if id_confirmed else f" Employee Id could not be confirmed (found '{actual_id}')."
                logger.info("Employee creation verified: %s", detail)
                shot = self._screenshot("05_verification")
                return self._record(step, "success", detail, shot)

            shot = self._screenshot("05_verification_mismatch")
            return self._record(
                step, "warning",
                f"Employee saved, but verification is incomplete (url={url_confirmed}, name={name_confirmed}, id={id_confirmed}).",
                shot,
            )
        except TimeoutException:
            shot = self._screenshot("05_verification_timeout")
            return self._record(step, "failed", "Could not verify employee creation.", shot)

    def _scrape_visible_rows(self, limit: int):
        # NOTE: ".oxd-table-card" wraps ".oxd-table-row" for the same
        # employee (nested, not siblings). Selecting both in one CSS
        # union matched each employee twice and duplicated every row in
        # the table/CSV. ".oxd-table-body .oxd-table-row" alone is the
        # one true per-employee row.
        rows = self.driver.find_elements(By.CSS_SELECTOR, ".oxd-table-body .oxd-table-row")
        records = []
        for row in rows[:limit]:
            try:
                cells = row.find_elements(By.CSS_SELECTOR, ".oxd-table-cell, .oxd-table-cell-content")
                cell_texts = [c.text.strip() for c in cells if c.text.strip()]
                if len(cell_texts) >= 3:
                    records.append(cell_texts)
            except StaleElementReferenceException:
                continue

        if not records:
            # Fallback for a differently-structured table (e.g. card layout
            # without .oxd-table-row), scanning .oxd-table-card directly.
            fallback_rows = self.driver.find_elements(By.CSS_SELECTOR, ".oxd-table-card")
            for row in fallback_rows[:limit]:
                cells = row.find_elements(By.CSS_SELECTOR, ".oxd-table-cell, .oxd-table-cell-content")
                texts = [c.text.strip() for c in cells if c.text.strip()]
                if len(texts) >= 3:
                    records.append(texts)
        return records

    def _employee_id_search_input(self):
        return self.driver.find_element(
            By.XPATH,
            "//label[normalize-space()='Employee Id']/ancestor::div[contains(@class, 'oxd-input-group')]//input",
        )

    def _search_employee_by_id(self, employee_id: str, retries: int = 3):
        """Use OrangeHRM's own Employee Id search filter to reliably find a
        specific employee, independent of the default table's sort order or
        row cap. Returns the row's cell texts, or None only when the search
        genuinely completed with zero matching rows.

        The whole lookup is retried on StaleElementReferenceException: the
        Employee List page does an async data fetch after load, and its
        filter-panel Vue component can re-render once that data arrives,
        invalidating an element reference captured before it did (the same
        class of issue fixed in add_employee(), here applied to the search
        filter and result rows).
        """
        last_exc = None
        for attempt in range(retries):
            try:
                base_url = self.base_url.replace("/auth/login", "")
                self.driver.get(f"{base_url}/pim/viewEmployeeList")
                self.wait.until(EC.presence_of_element_located((By.XPATH, "//label[normalize-space()='Employee Id']")))
                self.wait_for_form_to_be_ready(25)

                self._stale_safe(self._employee_id_search_input, lambda el: self._set_field_value(el, employee_id))

                search_btn = self.driver.find_element(By.XPATH, "//button[normalize-space()='Search']")
                self.click_element_safely(search_btn)
                self.wait_for_form_to_be_ready(25)
                self.wait.until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".oxd-table-body .oxd-table-row")),
                        EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'No Records Found')]")),
                    )
                )

                for row in self.driver.find_elements(By.CSS_SELECTOR, ".oxd-table-body .oxd-table-row"):
                    try:
                        cells = row.find_elements(By.CSS_SELECTOR, ".oxd-table-cell, .oxd-table-cell-content")
                        texts = [c.text.strip() for c in cells if c.text.strip()]
                    except StaleElementReferenceException:
                        raise  # let the outer retry re-run the whole search rather than skip a row
                    if len(texts) >= 1 and texts[0] == employee_id:
                        return texts
                return None
            except StaleElementReferenceException as exc:
                last_exc = exc
                logger.warning(
                    "Stale element while searching for employee id '%s' (attempt %s/%s); retrying: %s",
                    employee_id, attempt + 1, retries, exc,
                )
                time.sleep(0.5)
            except (TimeoutException, NoSuchElementException, WebDriverException) as exc:
                logger.warning("Direct search for employee id '%s' failed: %s: %s", employee_id, type(exc).__name__, exc)
                return None
        logger.warning(
            "Direct search for employee id '%s' failed after %s attempts due to repeated stale elements: %s",
            employee_id, retries, last_exc,
        )
        return None

    def extract_employee_list(self, limit: int = 50, ensure_employee_id: str = None):
        step = "Extract Employee List"
        try:
            logger.info("Employee list extraction started.")
            base_url = self.base_url.replace("/auth/login", "")
            self.driver.get(f"{base_url}/pim/viewEmployeeList")
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-body")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-card")),
                    EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-filter")),
                )
            )
            self.wait_for_form_to_be_ready(25)
            logger.info("Employee list opened and table loaded.")

            records = self._scrape_visible_rows(limit)

            # OrangeHRM's default table is sorted alphabetically and this
            # page only renders `limit` rows, so a genuinely-created new
            # employee can fall outside that window and silently disappear
            # from the dashboard/CSV even though it really exists on the
            # site. Guarantee it's present using a direct, targeted lookup
            # via OrangeHRM's own Employee Id search (real data, not a
            # fabricated row) rather than trusting pagination/sort order.
            if ensure_employee_id and not any(rec and rec[0] == ensure_employee_id for rec in records):
                found_record = self._search_employee_by_id(ensure_employee_id)
                if found_record:
                    records.insert(0, found_record)
                    logger.info(
                        "New employee id '%s' fell outside the default table page; added via direct Employee Id search.",
                        ensure_employee_id,
                    )
                else:
                    logger.warning(
                        "New employee id '%s' could not be confirmed in the Employee List even via direct search.",
                        ensure_employee_id,
                    )
                # Re-open the unfiltered list so the page/screenshot/URL left
                # behind reflects the general list, not the search filter.
                self.driver.get(f"{base_url}/pim/viewEmployeeList")
                self.wait.until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-body")),
                        EC.presence_of_element_located((By.CLASS_NAME, "oxd-table-card")),
                    )
                )
                self.wait_for_form_to_be_ready(25)

            if not records:
                logger.warning("Employee list extraction produced zero rows; CSV will contain header only.")

            os.makedirs(Config.DATA_DIR, exist_ok=True)
            with open(Config.CSV_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Employee Id", "First Name", "Last Name", "Job Title", "Sub Unit", "Status"])
                for rec in records:
                    writer.writerow(rec[:6])
            logger.info("CSV generated: %s (%d record(s)).", Config.CSV_FILE, len(records))

            shot = self._screenshot("06_employee_list")
            logger.info("Employee list extracted: %d record(s).", len(records))
            return self._record(
                step, "success", f"Extracted {len(records)} employee record(s) to CSV.", shot
            ), records
        except (TimeoutException, NoSuchElementException, WebDriverException) as exc:
            logger.error("Employee list extraction failed: %s: %s", type(exc).__name__, exc)
            shot = self._screenshot("06_extract_error")
            return self._record(step, "failed", f"Could not extract employee list: {type(exc).__name__}: {exc}", shot), []

    def logout(self):
        step = "Logout"
        try:
            logger.info("Logout started.")
            user_dropdown = self.wait.until(
                EC.element_to_be_clickable((By.CLASS_NAME, "oxd-userdropdown-tab"))
            )
            user_dropdown.click()
            logout_link = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[text()='Logout']"))
            )
            logout_link.click()
            self.wait.until(EC.presence_of_element_located((By.NAME, "username")))
            logger.info("Logout successful.")
            shot = self._screenshot("07_logout")
            return self._record(step, "success", "Logged out successfully.", shot)
        except (TimeoutException, NoSuchElementException) as exc:
            logger.error("Logout failed: %s: %s", type(exc).__name__, exc)
            shot = self._screenshot("07_logout_error")
            return self._record(step, "failed", f"Logout failed: {type(exc).__name__}: {exc}", shot)

    # ------------------------------------------------------------------ #
    # Orchestrator
    # ------------------------------------------------------------------ #
    def run_full_flow(self, username: str, password: str, first_name: str, last_name: str, employee_id: str = None):
        """Run the complete dashboard-triggered flow end to end and return structured result data."""
        result = {
            "overall_status": "success",
            "message": "Automation completed successfully.",
            "inserted_employee": {
                "first_name": first_name,
                "last_name": last_name,
                "employee_id": employee_id or "system-assigned",
            },
            "extracted_records": [],
            "csv_file": None,
            "timeline": [],
            "error": None,
            "completed_steps": [],
            "before_screenshot": None,
            "after_screenshot": None,
        }
        logger.info("Automation started.")
        logger.info(
            "Dashboard data received: user='%s' employee='%s %s' requested_id='%s'.",
            username, first_name, last_name, employee_id or "auto",
        )
        try:
            self.start_driver()
            self._record_and_stop_on_critical_failure(self.open_site)
            self._record_and_stop_on_critical_failure(self.login, username, password)
            self._record_and_stop_on_critical_failure(self.navigate_to_pim)

            # Before/After widget: capture the Employee List as it looks
            # BEFORE the new employee exists, ahead of Add Employee.
            result["before_screenshot"] = self.capture_before_state()

            self._record_and_stop_on_critical_failure(self.add_employee, first_name, last_name, employee_id)
            # add_employee may have regenerated the id (duplicate handling) or
            # captured OrangeHRM's system-assigned id - reflect the real value.
            result["inserted_employee"]["employee_id"] = self.last_employee_id or "system-assigned"

            verify_entry = self.verify_employee_created(first_name, last_name, self.last_employee_id)
            if verify_entry["status"] == "failed":
                raise AutomationError("Employee creation verification failed.")
            result["completed_steps"].append("Employee verified")

            # Before/After widget: capture the Employee List refreshed AFTER
            # the new employee was created, so it's visible in the table.
            result["after_screenshot"] = self.capture_after_state()

            extract_result, records = self.extract_employee_list(ensure_employee_id=self.last_employee_id)
            result["extracted_records"] = records
            if extract_result["status"] == "failed":
                raise AutomationError("Employee list extraction failed.")
            if os.path.exists(Config.CSV_FILE):
                result["csv_file"] = "data/employees_extracted.csv"
            result["completed_steps"].append("Employee list extracted")

            logout_entry = self.logout()
            if logout_entry["status"] == "failed":
                # Logout is a mandatory step for a true SUCCESS verdict. Don't
                # raise (extraction/CSV already succeeded and are worth
                # keeping), but do NOT record it as completed - the final
                # timeline scan below will correctly downgrade the overall
                # status to partial_failure because of this failed entry.
                logger.warning("Logout failed after a successful run: %s", logout_entry["message"])
            else:
                result["completed_steps"].append("Logout completed")
            result["message"] = "Automation completed successfully."

        except AutomationError as exc:
            logger.exception("Automation halted due to a critical failure")
            self._record("Automation Halted", "failed", str(exc))
            result["overall_status"] = "failed"
            result["message"] = str(exc)
            result["error"] = str(exc)
        except Exception as exc:
            logger.exception("Unexpected fatal exception")
            self._record("Automation Halted", "failed", f"Unexpected error: {exc}")
            result["overall_status"] = "failed"
            result["message"] = f"Unexpected error: {exc}"
            result["error"] = str(exc)
        finally:
            try:
                self.quit_driver()
            except Exception:
                logger.warning("Browser shutdown failed during final cleanup.")

        result["timeline"] = self.timeline

        # Final verdict: HTTP 200 alone is not success. SUCCESS requires every
        # mandatory step to have actually reported "success" AND a real,
        # non-empty CSV to exist on disk. Anything less is partial_failure
        # (some steps worked) or failed (nothing did), with the exact
        # missing/failed step(s) named.
        step_status = {t["step"]: t["status"] for t in self.timeline}
        mandatory_steps = [
            "Open OrangeHRM", "Login", "Navigate to PIM", "Add Employee",
            "Verify Creation", "Extract Employee List", "Logout",
        ]
        csv_ok = bool(result["csv_file"]) and os.path.exists(Config.CSV_FILE) and os.path.getsize(Config.CSV_FILE) > 0
        incomplete_steps = [s for s in mandatory_steps if step_status.get(s) != "success"]
        if not csv_ok:
            incomplete_steps.append("CSV generation")

        if not incomplete_steps:
            result["overall_status"] = "success"
            result["message"] = "Automation completed successfully."
        elif any(status == "success" for status in step_status.values()):
            result["overall_status"] = "partial_failure"
            if not result.get("error"):
                result["message"] = f"Automation finished with incomplete/failed step(s): {', '.join(incomplete_steps)}."
        else:
            result["overall_status"] = "failed"

        logger.info("Automation completed: overall_status=%s.", result["overall_status"])
        return result

    def _record_and_stop_on_critical_failure(self, fn, *args):
        entry = fn(*args)
        if entry["status"] == "failed":
            raise AutomationError(f"Stopped after critical failure in step: {entry['step']}")
        return entry
