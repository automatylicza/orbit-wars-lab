/**
 * Settings view — Kaggle integration (paste token from kaggle.com/settings).
 * Sibling to Leaderboard in the top nav.
 */

import { api, KaggleAuthStatus } from "../api";
import { installHeaderNav } from "../components/header-nav";
import { escapeHtml } from "../utils/escape";

// Validation round-trip goes through kaggle.com; allow generous headroom over
// the 10s backend timeout so we see the server's error rather than our own.
const SAVE_TIMEOUT_MS = 15000;

export async function renderSettings(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <main class="dashboard settings-view">
      <section>
        <h2>Settings</h2>

        <div class="settings-group">
          <div class="settings-group-head">
            <h3>Kaggle integration</h3>
            <div id="kauth-status" class="kauth-status">Checking…</div>
          </div>

          <div id="kauth-body" class="kauth-body"></div>

          <p class="settings-privacy">
            Your token is stored on this machine at
            <code>~/.kaggle/kaggle.json</code> (chmod 600) — the standard Kaggle
            CLI location. The backend never sends it back to your browser, and
            it isn't transmitted anywhere except to Kaggle itself when you use
            the Submissions tab. Kaggle credentials are also <strong>stripped from the
            environment</strong> of forked agent subprocesses, so third-party
            bots in <code>agents/external/</code> can't read them.
          </p>
        </div>
      </section>
    </main>
  `;
  installHeaderNav(root, "settings");

  await renderAuthSection();
}

async function renderAuthSection(): Promise<void> {
  const statusEl = document.getElementById("kauth-status")!;
  const bodyEl = document.getElementById("kauth-body")!;
  statusEl.textContent = "Checking…";
  statusEl.className = "kauth-status";
  bodyEl.innerHTML = "";

  let status: KaggleAuthStatus;
  try {
    status = await api.getKaggleAuthStatus();
  } catch (e) {
    statusEl.textContent = "Status unavailable";
    statusEl.classList.add("err");
    bodyEl.innerHTML = `<div class="kauth-error">${escapeHtml((e as Error).message)}</div>`;
    return;
  }

  if (status.connected && status.username) {
    const sourceBadge = status.source === "env"
      ? `<span class="kauth-source-badge">via env vars</span>`
      : "";
    statusEl.innerHTML =
      `<span class="kauth-dot ok"></span>Connected as <strong>${escapeHtml(status.username)}</strong>${sourceBadge}`;
    statusEl.classList.add("ok");
    if (status.source === "env") {
      renderEnvConnectedBody(bodyEl, status.username);
    } else {
      renderFileConnectedBody(bodyEl, status.username);
    }
  } else {
    statusEl.innerHTML = `<span class="kauth-dot"></span>Not connected`;
    renderSetupBody(bodyEl);
  }
}

function renderFileConnectedBody(bodyEl: HTMLElement, _username: string): void {
  bodyEl.innerHTML = `
    <div class="kauth-actions-row">
      <button id="kauth-replace" class="scrape-btn cancel">Replace token</button>
      <button id="kauth-disconnect" class="scrape-btn cancel">Disconnect</button>
    </div>
    <div id="kauth-replace-panel" hidden></div>
    <div id="kauth-msg" class="kauth-msg" hidden></div>
  `;

  document.getElementById("kauth-disconnect")!.addEventListener("click", async () => {
    const ok = window.confirm(
      "Disconnect your Kaggle token?\n\n" +
        "This deletes ~/.kaggle/kaggle.json. Your token on kaggle.com stays valid " +
        "— you can always paste it back. Submissions tab will stop working until " +
        "you reconnect.",
    );
    if (!ok) return;
    const msg = document.getElementById("kauth-msg")!;
    msg.hidden = false;
    msg.className = "kauth-msg";
    msg.textContent = "Disconnecting…";
    try {
      await api.clearKaggleAuth();
      await renderAuthSection();
    } catch (e) {
      msg.className = "kauth-msg err";
      msg.textContent = `Error: ${(e as Error).message}`;
    }
  });

  document.getElementById("kauth-replace")!.addEventListener("click", () => {
    const panel = document.getElementById("kauth-replace-panel")!;
    if (panel.hidden) {
      panel.hidden = false;
      panel.innerHTML = "";
      mountTokenForm(panel, "Save new token");
    } else {
      panel.hidden = true;
      panel.innerHTML = "";
    }
  });
}

function renderEnvConnectedBody(bodyEl: HTMLElement, username: string): void {
  // Env vars win over the config file, so "Disconnect" and "Replace" don't
  // meaningfully change the active credentials. Make that explicit instead of
  // showing buttons that would silently do nothing.
  bodyEl.innerHTML = `
    <div class="kauth-env-note">
      <strong>Token is set via environment variables.</strong>
      <p>
        The Kaggle SDK is using <code>KAGGLE_USERNAME</code> and
        <code>KAGGLE_KEY</code> from this process's environment
        (currently <strong>${escapeHtml(username)}</strong>). They take
        precedence over <code>~/.kaggle/kaggle.json</code>, so pasting a
        different token here wouldn't change anything.
      </p>
      <p>
        To disconnect or switch accounts, unset the env vars in the shell
        where you launched the backend (or remove them from your Docker
        compose / systemd unit), then restart.
      </p>
    </div>
  `;
}

function renderSetupBody(bodyEl: HTMLElement): void {
  bodyEl.innerHTML = `
    <div class="kauth-steps">
      <p>To connect your Kaggle account, paste a Kaggle API token below. Two formats accepted:</p>
      <ul>
        <li>
          <strong>New format (access token, recommended):</strong>
          on <a href="https://www.kaggle.com/settings/account" target="_blank" rel="noopener">kaggle.com/settings/account</a>
          → <strong>API</strong> → click <em>"Generate API Token"</em> (or similar)
          → copy the <code>KGAT_…</code> string and paste it here directly.
        </li>
        <li>
          <strong>Legacy format (kaggle.json):</strong>
          if Kaggle still shows <em>"Create New Token"</em>, that downloads a
          <code>kaggle.json</code> file with
          <code>{"username":"…","key":"…"}</code> — paste its full contents.
        </li>
      </ul>
      <p>
        Either way, <strong>accept the
        <a href="https://www.kaggle.com/competitions/orbit-wars/rules" target="_blank" rel="noopener">Orbit Wars competition rules</a></strong>
        on Kaggle first, otherwise the token can validate but won't be allowed
        to list your submissions.
      </p>
    </div>
    <div id="kauth-form-mount"></div>
  `;
  mountTokenForm(document.getElementById("kauth-form-mount")!, "Test & save");
}

function mountTokenForm(host: HTMLElement, submitLabel: string): void {
  host.innerHTML = `
    <div class="kauth-form">
      <label class="kauth-label">
        Paste a <code>KGAT_…</code> access token <em>or</em> the contents of <code>kaggle.json</code>
        <textarea id="kauth-token" class="kauth-token" rows="4"
          placeholder='KGAT_… (or {"username":"…","key":"…"})'
          spellcheck="false" autocapitalize="off" autocomplete="off"></textarea>
      </label>
      <div class="kauth-form-row">
        <button id="kauth-save" class="scrape-btn go">${escapeHtml(submitLabel)}</button>
        <span id="kauth-form-msg" class="kauth-msg" hidden></span>
      </div>
    </div>
  `;

  const textarea = host.querySelector<HTMLTextAreaElement>("#kauth-token")!;
  const saveBtn = host.querySelector<HTMLButtonElement>("#kauth-save")!;
  const msgEl = host.querySelector<HTMLSpanElement>("#kauth-form-msg")!;

  saveBtn.addEventListener("click", async () => {
    const token = textarea.value.trim();
    if (!token) {
      msgEl.hidden = false;
      msgEl.className = "kauth-msg err";
      msgEl.textContent = "Paste the token first.";
      return;
    }
    saveBtn.disabled = true;
    textarea.disabled = true;
    msgEl.hidden = false;
    msgEl.className = "kauth-msg";
    msgEl.innerHTML = `<span class="kauth-spinner"></span>Validating with Kaggle…`;

    const controller = new AbortController();
    const timeoutHandle = window.setTimeout(() => controller.abort(), SAVE_TIMEOUT_MS);
    try {
      const result = await api.saveKaggleAuth(token, controller.signal);
      textarea.value = "";
      if (result.shadowed) {
        msgEl.className = "kauth-msg warn";
        msgEl.innerHTML =
          `Saved, but environment variables shadow the file. ` +
          `Active user stays <strong>${escapeHtml(result.username ?? "")}</strong>.`;
      } else {
        msgEl.className = "kauth-msg ok";
        msgEl.textContent = "Saved.";
      }
      setTimeout(() => void renderAuthSection(), 600);
    } catch (e) {
      const err = e as Error & { status?: number; name?: string };
      msgEl.className = "kauth-msg err";
      if (err.name === "AbortError") {
        msgEl.textContent = `Validation timed out after ${Math.round(SAVE_TIMEOUT_MS / 1000)}s. Check your network and retry.`;
      } else {
        msgEl.textContent = err.message || "Save failed.";
      }
    } finally {
      window.clearTimeout(timeoutHandle);
      saveBtn.disabled = false;
      textarea.disabled = false;
    }
  });
}

