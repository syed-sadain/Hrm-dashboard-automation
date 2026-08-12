/**
 * Dashboard controller.
 * Submits the form to /run-automation, then replays the returned timeline
 * onto the pipeline UI with a short stagger so each stage feels "live"
 * even though the Flask call itself is synchronous.
 */
(() => {
  const form = document.getElementById("automationForm");
  const runBtn = document.getElementById("runBtn");
  const formNote = document.getElementById("formNote");
  const statusPill = document.getElementById("statusPill");
  const pipeline = document.getElementById("pipeline");
  const downloadCsvBtn = document.getElementById("downloadCsvBtn");

  const STEP_STAGGER_MS = 550;

  function resetPipeline() {
    document.querySelectorAll(".pipe-step").forEach((el) => {
      el.classList.remove("is-running", "is-success", "is-failed", "is-warning", "is-done");
      el.querySelector(".pipe-msg").textContent = "Waiting to start…";
    });
  }

  function setStatusPill(state, label) {
    statusPill.className = `pill pill-live state-${state}`;
    statusPill.innerHTML = `<span class="dot"></span> ${label}`;
  }

  function applyStepResult(entry) {
    const stepEl = pipeline.querySelector(`.pipe-step[data-step="${cssEscape(entry.step)}"]`);
    if (!stepEl) return;
    stepEl.classList.add("is-done");
    stepEl.classList.remove("is-running");
    stepEl.classList.add(`is-${entry.status === "success" ? "success" : entry.status === "warning" ? "warning" : "failed"}`);
    stepEl.querySelector(".pipe-msg").textContent = `${entry.timestamp} · ${entry.message}`;
  }

  function markRunning(stepName) {
    const stepEl = pipeline.querySelector(`.pipe-step[data-step="${cssEscape(stepName)}"]`);
    if (stepEl) {
      stepEl.classList.add("is-running");
      stepEl.querySelector(".pipe-msg").textContent = "Running…";
    }
  }

  function cssEscape(str) {
    return str.replace(/["\\]/g, "\\$&");
  }

  function playTimeline(timeline) {
    return new Promise((resolve) => {
      let i = 0;
      function next() {
        if (i >= timeline.length) return resolve();
        const entry = timeline[i];
        markRunning(entry.step);
        setTimeout(() => {
          applyStepResult(entry);
          i += 1;
          next();
        }, STEP_STAGGER_MS);
      }
      next();
    });
  }

  function renderEmployeeEcho(employee) {
    document.getElementById("echoFirst").textContent = employee.first_name || "—";
    document.getElementById("echoLast").textContent = employee.last_name || "—";
    document.getElementById("echoId").textContent = employee.employee_id || "—";
  }

  function renderScreenshots(data) {
    // Real proof of the automation working: the Employee List page before
    // the new hire existed vs. after (refreshed) it was added — not the
    // login-page skeleton vs. logout-page timeline endpoints.
    const beforeEl = document.getElementById("shotBefore");
    const afterEl = document.getElementById("shotAfter");

    if (data.before_screenshot) {
      beforeEl.innerHTML = `<img src="/static/${data.before_screenshot}" alt="Employee List before the automation ran" />`;
    } else {
      beforeEl.innerHTML = `<span class="shot-placeholder">Before screenshot unavailable</span>`;
    }

    if (data.after_screenshot) {
      afterEl.innerHTML = `<img src="/static/${data.after_screenshot}" alt="Employee List after the automation ran" />`;
    } else {
      afterEl.innerHTML = `<span class="shot-placeholder">After screenshot unavailable</span>`;
    }
  }

  function renderTable(records) {
    const tbody = document.getElementById("employeeTableBody");
    const countEl = document.getElementById("tableCount");
    tbody.innerHTML = "";

    if (!records || records.length === 0) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="6">No records extracted this run.</td></tr>`;
      countEl.textContent = "";
      return;
    }

    countEl.textContent = `(${records.length})`;
    records.forEach((row) => {
      const tr = document.createElement("tr");
      // Pad/truncate to 6 columns defensively — live DOM structure can vary.
      const cells = [...row];
      while (cells.length < 6) cells.push("—");
      tr.innerHTML = cells.slice(0, 6).map((c) => `<td>${escapeHtml(c)}</td>`).join("");
      tbody.appendChild(tr);
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const payload = {
      username: document.getElementById("username").value.trim(),
      password: document.getElementById("password").value,
      first_name: document.getElementById("first_name").value.trim(),
      last_name: document.getElementById("last_name").value.trim(),
      employee_id: document.getElementById("employee_id").value.trim(),
    };

    if (!payload.username || !payload.password) {
      formNote.textContent = "Username and password are required.";
      formNote.className = "form-note is-error";
      return;
    }

    if (!payload.first_name || !payload.last_name) {
      formNote.textContent = "First name and last name are required.";
      formNote.className = "form-note is-error";
      return;
    }

    resetPipeline();
    formNote.textContent = "";
    formNote.className = "form-note";
    runBtn.disabled = true;
    runBtn.classList.add("is-loading");
    setStatusPill("running", "Running");
    downloadCsvBtn.disabled = true;

    try {
      const res = await fetch("/run-automation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (res.status === 400) {
        formNote.textContent = (data.errors || ["Validation failed."]).join(" ");
        formNote.className = "form-note is-error";
        setStatusPill("failed", "Validation error");
        return;
      }

      await playTimeline(data.timeline || []);

      const insertedEmployee = data.inserted_employee || data.employee || {};
      renderEmployeeEcho(insertedEmployee);
      renderScreenshots(data);
      renderTable(data.extracted_records || []);

      if (data.csv_file || data.csv_path) {
        downloadCsvBtn.disabled = false;
      }

      if (data.overall_status === "success") {
        formNote.textContent = "Automation completed successfully end to end.";
        formNote.className = "form-note is-success";
        setStatusPill("success", "Success");
      } else if (data.overall_status === "partial_failure") {
        formNote.textContent = "Automation finished with some steps failed — see pipeline above.";
        formNote.className = "form-note is-error";
        setStatusPill("failed", "Partial failure");
      } else {
        formNote.textContent = data.error || "Automation failed.";
        formNote.className = "form-note is-error";
        setStatusPill("failed", "Failed");
      }
    } catch (err) {
      formNote.textContent = `Network or server error: ${err.message}`;
      formNote.className = "form-note is-error";
      setStatusPill("failed", "Error");
    } finally {
      runBtn.disabled = false;
      runBtn.classList.remove("is-loading");
    }
  });

  downloadCsvBtn.addEventListener("click", () => {
    window.location.href = "/download-csv";
  });
})();
