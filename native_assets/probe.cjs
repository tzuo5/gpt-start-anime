// Injected into a TEMPORARY test archive only; removed before activation.
'use strict';
const { app, BrowserWindow, dialog } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const config = __NATIVE_PROBE_CONFIG__;
console.log('[startup-animation-probe] registered', config.phase);
let finished = false;
let started = false;
let child;
dialog.showMessageBox = async (...args) => {
  const options = args.at(-1);
  await finish({ ok: false, phase: config.phase,
    error: 'Application startup dialog: ' + options.message,
    detail: options.detail });
  return { response: options.cancelId ?? 0 };
};
app.on('will-quit', () => {
  if (!finished) fs.writeFileSync(config.report, JSON.stringify({ok:false, phase:config.phase, error:'Application quit before the native interface was ready'}));
});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function finish(result) {
  if (finished) return;
  finished = true;
  if (child && child.exitCode === null) child.kill();
  fs.writeFileSync(config.report, JSON.stringify(result, null, 2));
  app.quit();
  setTimeout(() => app.exit(result.ok ? 0 : 1), 1000).unref();
}
const deadline = setTimeout(() => finish({ ok: false, phase: config.phase, error: 'Isolated app probe timed out' }), 60000);
async function check(win) {
  try {
    if (config.phase === 'raw') {
      let content;
      for (let i = 0; i < 100 && !finished; i++) {
        content = await win.webContents.executeJavaScript('({url:location.href, length:document.body.innerText.length})');
        if (content.length > 0) break;
        await sleep(400);
      }
      return finish({ ok: content.length > 0, phase: 'raw', content });
    }
    // Wait until createWindow's initial load promise and React bootstrap finish.
    // Navigating inside did-finish-load immediately aborts that promise.
    for (let i = 0; i < 80 && !finished; i++) {
      const ready = await win.webContents.executeJavaScript('document.body.innerText.length > 0');
      if (ready) break;
      await sleep(400);
    }
    await sleep(500);
    await win.webContents.loadURL('app://-/index.html?initialRoute=%2Fsettings%2Fappearance');
    let content;
    for (let i = 0; i < 100 && !finished; i++) {
      content = await win.webContents.executeJavaScript(`({url:location.href, entries:document.querySelectorAll('[data-codex-startup-animation]').length, text:document.body.innerText.slice(0,1000)})`);
      if (content.entries === 1) break;
      await sleep(400);
    }
    if (content.entries !== 1) return finish({ ok: false, phase: 'patched', error: 'Appearance entry did not render', content });
    const bridge = require('./startup-animation-bridge.cjs');
    const click = () => win.webContents.executeJavaScript(`document.querySelector('[data-codex-startup-animation] button').click()`);
    await click();
    await sleep(900);
    child = bridge.child();
    if (!child || child.exitCode !== null)
      return finish({ ok: false, phase: 'patched', error: 'Settings process did not start', content });
    const firstPid = child.pid;
    await click();
    await sleep(600);
    const duplicateReused = bridge.child()?.pid === firstPid;
    const colors = [];
    for (const theme of ['light', 'dark']) {
      const selected = await win.webContents.executeJavaScript(`(()=>{const modes=document.querySelectorAll('input[name="appearance-theme"]');if(modes.length!==3)return false;modes[${theme === 'light' ? 1 : 2}].click();return true})()`);
      if (!selected) throw new Error('Native appearance mode selector is missing');
      await sleep(500);
      colors.push(await win.webContents.executeJavaScript(`(()=>{const el=document.querySelector('[data-codex-startup-animation]');const button=el.querySelector('button');button.focus();const s=getComputedStyle(el);return {theme:${JSON.stringify(theme)}, color:s.color, border:s.borderColor, keyboardFocusable:document.activeElement===button, alerts:el.querySelector('[role=alert]')?.textContent||''}})()`));
      const image = await win.webContents.capturePage();
      fs.writeFileSync(path.join(path.dirname(config.report), `appearance-${theme}.png`), image.toPNG());
    }
    win.focus();
    await sleep(150);
    await win.webContents.executeJavaScript(`(()=>{const target=document.querySelector('[data-codex-startup-animation] button');window.__startupProbeClicks=0;target.addEventListener('click',()=>window.__startupProbeClicks++);const items=Array.from(document.querySelectorAll('button,input,select,a[href],[tabindex="0"]')).filter(e=>!e.disabled&&e.tabIndex>=0&&e.getClientRects().length);const i=items.indexOf(target);items[i-1].focus()})()`);
    win.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'Tab' });
    win.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'Tab' });
    await sleep(150);
    const keyboardTabFocus = await win.webContents.executeJavaScript(`document.activeElement===document.querySelector('[data-codex-startup-animation] button')`);
    win.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'Return' });
    win.webContents.sendInputEvent({ type: 'char', keyCode: '\r' });
    win.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'Return' });
    await sleep(500);
    const keyboardActivation = await win.webContents.executeJavaScript('window.__startupProbeClicks > 0') && bridge.child()?.pid === firstPid;
    // Fault injection is confined to the temporary test archive and this path.
    // The real installed helper is never renamed or edited.
    child.kill();
    for (let i = 0; i < 30 && child.exitCode === null; i++) await sleep(100);
    const originalExists = fs.existsSync;
    let missingHelperError;
    try {
      fs.existsSync = file => file === config.settingsPath ? false : originalExists(file);
      await click();
      await sleep(400);
      missingHelperError = await win.webContents.executeJavaScript(`document.querySelector('[data-codex-startup-animation] [role="alert"]')?.textContent || ''`);
    } finally { fs.existsSync = originalExists; }
    // A second, untrusted top-level page gets the same preload but no authority.
    const outsider = new BrowserWindow({ show: false, webPreferences: {
      preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true
    }});
    await outsider.loadURL('data:text/html,<p>Untrusted probe</p>');
    const denied = await outsider.webContents.executeJavaScript('window.codexStartupAnimation.openSettings()');
    outsider.destroy();
    clearTimeout(deadline);
    return finish({ ok: duplicateReused && keyboardTabFocus && keyboardActivation && Boolean(missingHelperError) && denied.ok === false && colors[0].color !== colors[1].color && colors.every(c => c.keyboardFocusable && !c.alerts),
      phase: 'patched', entries: content.entries, duplicateReused, keyboardTabFocus, keyboardActivation,
      missingHelperError, untrustedDenied: !denied.ok, colors });
  } catch (error) { return finish({ ok: false, phase: config.phase, error: String(error.stack || error) }); }
}
app.on('browser-window-created', (_, win) => {
  win.webContents.on('did-finish-load', () => {
    if (started || finished) return;
    let url;
    try { url = new URL(win.webContents.getURL()); } catch { return; }
    if (url.protocol !== 'app:' || url.hostname !== '-' || url.pathname !== '/index.html') return;
    started = true;
    check(win);
  });
});
