'use strict';
const { ipcMain, BrowserWindow } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const channel = 'codex-startup-animation:open-settings';
// Filled with the absolute installed helper path by the per-user installer.
const settingsPath = __SETTINGS_PATH__;
let settingsChild = null;

function trusted(event) {
  try {
    const frame = event.senderFrame;
    const url = new URL(frame.url);
    return frame === event.sender.mainFrame &&
      BrowserWindow.fromWebContents(event.sender) !== null &&
      url.protocol === 'app:' && url.hostname === '-' &&
      url.pathname === '/index.html';
  } catch { return false; }
}

ipcMain.handle(channel, async (event, ...args) => {
  if (!trusted(event) || args.length) return { ok: false, error: 'Untrusted settings request' };
  if (settingsChild && settingsChild.exitCode === null && !settingsChild.killed)
    return { ok: true, reused: true };
  if (!fs.existsSync(settingsPath)) return { ok: false, error: 'Settings helper is missing. Reinstall the startup animation extension.' };
  return new Promise(resolve => {
    let completed = false;
    const child = spawn('/usr/bin/python3', [settingsPath, 'gui'], {
      shell: false, stdio: 'ignore', detached: true,
      env: { ...process.env, CODEX_STARTUP_SETTINGS_PARENT: String(process.pid) }
    });
    settingsChild = child;
    const finish = result => { if (!completed) { completed = true; resolve(result); } };
    child.once('error', error => {
      if (settingsChild === child) settingsChild = null;
      finish({ ok: false, error: error.message });
    });
    child.once('exit', code => {
      if (settingsChild === child) settingsChild = null;
      finish({ ok: false, error: `Settings window exited (${code}). Check GTK dependencies.` });
    });
    child.once('spawn', () => {
      child.unref();
      // Catch immediate import/display failures before reporting success.
      setTimeout(() => finish({ ok: true, reused: false }), 350);
    });
  });
});

// Main-process exports are for isolated tests, never exposed to the renderer.
module.exports = { trusted, child: () => settingsChild };
