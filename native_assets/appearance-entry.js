import { ifn as getReact, Xcn as getJSX, Pin as useIntl } from './app-shared-79b25ad8408c.js';
const React = getReact();
const JSX = getJSX();

export function StartupAnimationSettings() {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const intl = useIntl();
  const zh = String(intl.locale || navigator.language).toLowerCase().startsWith('zh');
  const title = zh ? '开屏动画' : 'Startup animation';
  const label = zh ? '开屏动画设置' : 'Startup animation settings';
  async function open() {
    setBusy(true);
    setError('');
    try {
      const result = await window.codexStartupAnimation.openSettings();
      if (!result?.ok) throw new Error(result?.error || 'Unable to open settings');
    } catch (err) { setError(String(err?.message || err)); }
    finally { setBusy(false); }
  }
  return JSX.jsxs('section', {
    'data-codex-startup-animation': 'v1', 'aria-label': title,
    className: 'rounded-xl border border-default p-4 mt-4',
    children: [
      JSX.jsxs('div', { className: 'flex items-center justify-between gap-4', children: [
        JSX.jsxs('div', { children: [
          JSX.jsx('h3', { className: 'font-medium', children: title }),
          JSX.jsx('p', { className: 'text-secondary text-sm mt-1', children: zh
            ? '设置 MP4 文件夹、播放开关、全屏和声音。'
            : 'Choose the MP4 folder, playback, fullscreen, and sound.' })
        ] }),
        JSX.jsx('button', {
          type: 'button', disabled: busy, onClick: open,
          className: 'rounded-lg border border-default px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50',
          children: busy ? (zh ? '正在打开…' : 'Opening…') : label
        })
      ] }),
      error && JSX.jsx('p', { role: 'alert', className: 'text-danger text-sm mt-2', children: error })
    ]
  });
}
