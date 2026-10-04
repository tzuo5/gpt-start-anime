'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { EventEmitter } = require('node:events');

function harness({ exists = true, spawnError = false, immediateExit = false } = {}) {
  let handler, count = 0, last;
  const electron = { app: {}, ipcMain: { handle: (_, fn) => { handler = fn; } },
    BrowserWindow: { fromWebContents: sender => sender.registered ? {} : null } };
  const spawn = (executable, args, options) => {
    assert.equal(executable, '/usr/bin/python3');
    assert.deepEqual(Array.from(args), ['/test/settings path/manage.py', 'gui']);
    assert.equal(options.shell, false);
    count++;
    last = new EventEmitter();
    last.exitCode = null; last.killed = false; last.unref = () => {};
    const child = last;
    setImmediate(() => {
      if (spawnError) child.emit('error', new Error('spawn failure'));
      else { child.emit('spawn'); if (immediateExit) { child.exitCode = 1; child.emit('exit', 1); } }
    });
    return child;
  };
  const source = fs.readFileSync(path.join(__dirname, '../native_assets/settings-bridge.cjs'), 'utf8')
    .replace('__SETTINGS_PATH__', JSON.stringify('/test/settings path/manage.py'));
  const context = { URL, process: { env: {}, pid: 100 }, module: { exports: {} },
    setTimeout: callback => setTimeout(callback, 10),
    require: name => name === 'electron' ? electron : name === 'node:child_process' ? { spawn }
      : name === 'node:fs' ? { existsSync: () => exists } : require(name) };
  vm.runInNewContext(source, context);
  function event(url = 'app://-/index.html', subframe = false, registered = true) {
    const frame = { url };
    return { senderFrame: frame, sender: { mainFrame: subframe ? {} : frame, registered } };
  }
  return { call: (...args) => handler(...args), event, count: () => count, last: () => last };
}

(async () => {
  const h = harness();
  for (const url of ['https://example.com', 'app://fs/@fs/index.html', 'app://-/other.html', 'file:///index.html', 'invalid'])
    assert.equal((await h.call(h.event(url))).ok, false);
  assert.equal((await h.call(h.event('app://-/index.html', true))).ok, false);
  assert.equal((await h.call(h.event('app://-/index.html', false, false))).ok, false);
  assert.equal((await h.call(h.event(), 'arbitrary-command')).ok, false);
  assert.equal(h.count(), 0);
  const opened = await h.call(h.event());
  assert.equal(opened.ok, true);
  assert.equal((await h.call(h.event())).reused, true);
  assert.equal(h.count(), 1);
  h.last().exitCode = 0; h.last().emit('exit', 0);
  assert.equal((await h.call(h.event())).ok, true);
  assert.equal(h.count(), 2);
  for (const options of [{ exists: false }, { spawnError: true }, { immediateExit: true }]) {
    const failure = harness(options);
    assert.equal((await failure.call(failure.event())).ok, false);
  }
  console.log('IPC origin, subframe, argument, single-child, missing-helper, and spawn-failure checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
