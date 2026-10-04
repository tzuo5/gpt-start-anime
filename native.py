"""Version-scoped, reversible native Appearance integration for Linux."""
import contextlib
import hashlib
import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import tempfile

from asar import Archive, digest_file

SOURCE = Path('/usr/lib/chatgpt')
SUPPORTED_VERSION = '26.930.31730'
SUPPORTED_SHA256 = '03157e5af93b354e0814956a3881d77354e62adcbffab5c7e630c14d3b66178c'
APPEARANCE = 'webview/assets/appearance-settings-68550b25f779.js'
EARLY = '.vite/build/early-bootstrap.js'
PRELOAD = '.vite/build/preload.js'
ASSETS = Path(__file__).parent / 'native_assets'


def adapter_hash():
    digest = hashlib.sha256()
    for path in [Path(__file__), Path(__file__).with_name('asar.py'),
                 *sorted(ASSETS.glob('*'))]:
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def root_path():
    from launcher import data_path
    return data_path() / 'native'


def state_path():
    return root_path() / 'state.json'


def write_json(path, data):
    from manage import atomic_write
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2).encode())


def fingerprint(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev]


def read_state():
    return json.loads(state_path().read_text()) if state_path().exists() else None


def status():
    try:
        state = read_state()
        if not state:
            return {'enabled': False, 'available': False, 'reason': '尚未安装原生 Appearance 集成'}
        state = dict(state)
        source = Path(state['source'])
        copy = Path(state['copy'])
        if fingerprint(source / 'resources/app.asar') != state['source_fingerprint'] or \
           fingerprint(source / 'ChatGPT') != state['binary_fingerprint']:
            reason = '系统应用已更新，需要重新适配；下次启动使用原版'
        elif not copy.is_dir() or fingerprint(copy / 'resources/app.asar') != state['copy_fingerprint'] or \
             fingerprint(copy / 'ChatGPT') != state['copy_binary_fingerprint']:
            reason = '应用副本缺失或已改变；下次启动使用原版'
        elif not state.get('validated'):
            reason = '副本尚未通过原生界面验收'
        elif state.get('adapter_hash') != adapter_hash():
            reason = '原生适配器已更新，需要重新构建副本；当前使用系统原版'
        else:
            if policy_required() and not policy_installed():
                return {**state, 'enabled': False, 'available': True,
                        'reason': '副本已通过验收；等待安装并加载专用 AppArmor 规则，当前使用系统原版'}
            reason = '原生入口已启用；正常退出 Codex 后，下次图标启动生效' if state.get('enabled') else '原生入口已关闭，使用系统原版'
            return {**state, 'available': True, 'reason': reason}
        return {**state, 'enabled': False, 'available': False, 'reason': reason}
    except (OSError, ValueError, KeyError, TypeError):
        return {'enabled': False, 'available': False, 'reason': '原生集成状态不可用，使用系统原版'}


def resolve_command(original):
    state = status()
    if state.get('enabled') and state.get('available') and original == state.get('original_command'):
        return [str(Path(state['copy']) / 'codex-launcher'), *original[1:]]
    return original


@contextlib.contextmanager
def locked():
    root_path().mkdir(parents=True, exist_ok=True)
    with (root_path() / 'install.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def patch_changes(archive, settings_path):
    appearance = archive.read(APPEARANCE).decode()
    needle = 'children:(0,h.jsx)(u,{defaultAdvancedExpanded:i},r)'
    if appearance.count(needle) != 1 or 'StartupAnimationSettings' in appearance:
        raise RuntimeError('Appearance 补丁锚点不匹配')
    appearance = 'import{StartupAnimationSettings as StartupEntry}from"./startup-animation-entry.js";' + appearance.replace(
        needle, 'children:(0,h.jsxs)(h.Fragment,{children:[(0,h.jsx)(u,{defaultAdvancedExpanded:i},r),(0,h.jsx)(StartupEntry,{})]})')
    preload = archive.read(PRELOAD).decode()
    if 'codexStartupAnimation' in preload or 'contextBridge.exposeInMainWorld' not in preload:
        raise RuntimeError('预加载补丁锚点不匹配')
    preload += '\nrequire("electron").contextBridge.exposeInMainWorld("codexStartupAnimation",Object.freeze({openSettings:()=>require("electron").ipcRenderer.invoke("codex-startup-animation:open-settings")}));\n'
    early = archive.read(EARLY).decode()
    if 'startup-animation-bridge' in early or 'require("electron")' not in early:
        raise RuntimeError('主进程补丁锚点不匹配')
    early = 'require("./startup-animation-bridge.cjs");\n' + early
    bridge = (ASSETS / 'settings-bridge.cjs').read_text().replace('__SETTINGS_PATH__', json.dumps(str(settings_path)))
    return {APPEARANCE: appearance.encode(), PRELOAD: preload.encode(), EARLY: early.encode(),
            '.vite/build/startup-animation-bridge.cjs': bridge.encode(),
            'webview/assets/startup-animation-entry.js': (ASSETS / 'appearance-entry.js').read_bytes()}


def probe(copy, phase, evidence):
    """Use a disposable archive/profile; no debug ports, no live user profile."""
    evidence.mkdir(parents=True, exist_ok=True)
    report = evidence / f'{phase}.json'
    report.unlink(missing_ok=True)
    archive_path = copy / 'resources/app.asar'
    pristine = copy / 'resources/app.asar.probe-backup'
    modified = copy / 'resources/app.asar.probe-new'
    archive = Archive(archive_path)
    from launcher import data_path
    probe_js = (ASSETS / 'probe.cjs').read_text().replace('__NATIVE_PROBE_CONFIG__', json.dumps({
        'phase': phase, 'report': str(report), 'settingsPath': str(data_path() / 'manage.py')}))
    archive.rewrite(modified, {EARLY: b'require("./startup-animation-probe.cjs");\n' + archive.read(EARLY),
                              '.vite/build/startup-animation-probe.cjs': probe_js.encode()})
    archive_path.rename(pristine)
    modified.rename(archive_path)
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix='codex-native-profile-') as profile:
            (Path(profile) / 'codex').mkdir(mode=0o700)
            if phase == 'patched':
                # Synthetic UI fixture, not a credential. No model request is made.
                # API-key mode exposes local Settings without reading a live login.
                auth = Path(profile) / 'codex/auth.json'
                auth.write_text(json.dumps({'OPENAI_API_KEY': 'sk-local-appearance-ui-fixture-not-a-real-key'}))
                auth.chmod(0o600)
                # Only the disposable profile has completed first-run onboarding.
                (Path(profile) / 'codex/.codex-global-state.json').write_text(json.dumps({
                    'electron-persisted-atom-state': {'electron:onboarding-projectless-completed': True}
                }))
            environment = dict(os.environ, CODEX_ELECTRON_USER_DATA_PATH=profile,
                               CODEX_HOME=str(Path(profile) / 'codex'),
                               XDG_CONFIG_HOME=str(Path(profile) / 'config'),
                               XDG_STATE_HOME=str(Path(profile) / 'state'),
                               XDG_DATA_HOME=str(Path(profile) / 'data'))
            # Do not reuse the invoking agent's pipes, identity, CLI or credentials.
            for key in list(environment):
                if key.startswith('CODEX_') and key not in ('CODEX_HOME', 'CODEX_ELECTRON_USER_DATA_PATH'):
                    environment.pop(key)
            for key in ('NODE_OPTIONS', 'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_ORGANIZATION', 'OPENAI_PROJECT'):
                environment.pop(key, None)
            with (evidence / f'{phase}.log').open('wb') as log:
                process = subprocess.Popen([str(copy / 'codex-launcher')], env=environment,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
                try:
                    process.wait(timeout=75)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
            if not report.exists():
                raise RuntimeError(f'{phase} 副本启动失败（exit={process.returncode}）。日志：{evidence / (phase + ".log")}；检查 AppArmor 权限和显示会话')
            result = json.loads(report.read_text())
            if not result.get('ok'):
                raise RuntimeError(f'{phase} 界面验收失败：{result.get("error", result)}；证据：{report}')
            return result
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        archive_path.unlink(missing_ok=True)
        pristine.rename(archive_path)


def profile_name():
    return f'codex-startup-animation-{os.getuid()}'


def policy_required():
    try:
        return Path('/sys/module/apparmor/parameters/enabled').read_text().strip() == 'Y' and \
            Path('/proc/sys/kernel/apparmor_restrict_unprivileged_userns').read_text().strip() == '1'
    except OSError:
        return False


def policy_installed():
    target = Path('/etc/apparmor.d') / profile_name()
    try:
        return not target.is_symlink() and target.stat().st_uid == 0 and \
            target.read_text() == apparmor_profile()
    except (OSError, ValueError):
        return False


def apparmor_profile():
    # Reject policy metacharacters instead of granting broader paths by accident.
    directory = str(root_path().resolve())
    if any(char in directory for char in '\n\r"\\*?[]{}'):
        raise ValueError('AppArmor 规则不支持当前数据目录中的特殊字符')
    return f'abi <abi/4.0>,\ninclude <tunables/global>\n\nprofile {profile_name()} "{directory}/versions/*/ChatGPT" flags=(unconfined) {{\n  userns,\n}}\n'


def prepare_apparmor():
    from manage import atomic_write
    target = root_path() / f'{profile_name()}.apparmor'
    atomic_write(target, apparmor_profile().encode(), 0o644)
    import shlex
    policy = '/etc/apparmor.d/' + profile_name()
    return f'规则已生成：{target}\n检查后执行（只安装副本专用规则）：\nsudo install -m 0644 -- {shlex.quote(str(target))} {shlex.quote(policy)}\nsudo apparmor_parser -r {shlex.quote(policy)}\n卸载规则：\nsudo apparmor_parser -R {shlex.quote(policy)}\nsudo rm -- {shlex.quote(policy)}'


def running_in(directory):
    directory = directory.resolve()
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            executable = Path(os.readlink(process / 'exe').removesuffix(' (deleted)'))
            if executable.is_relative_to(directory):
                return True
        except OSError:
            continue
    return False


def install(source=SOURCE):
    if os.geteuid() == 0:
        raise RuntimeError('请以普通用户运行安装器；只有 AppArmor 规则需要 sudo')
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
        raise RuntimeError('此适配器仅支持 Linux x86_64')
    from launcher import config_path, data_path, read_config
    from manage import install as install_launcher
    source = Path(source).resolve(strict=True)
    archive_path = source / 'resources/app.asar'
    archive = Archive(archive_path)
    package = json.loads(archive.read('package.json'))
    if package.get('name') != 'openai-codex-electron' or package.get('version') != SUPPORTED_VERSION or digest_file(archive_path) != SUPPORTED_SHA256:
        raise RuntimeError(f'未适配的应用包（版本 {package.get("version")}）；保留原有启动方式。支持 {SUPPORTED_VERSION} 的已核对 Linux 包')
    expected_source = fingerprint(archive_path)
    expected_binary = fingerprint(source / 'ChatGPT')
    # Refuse an unrelated target desktop entry rather than overriding its executable.
    if not config_path().exists():
        install_launcher()
    config = read_config(config_path())
    if Path(config['app_command'][0]).resolve() not in (source / 'codex-launcher', source / 'ChatGPT'):
        raise RuntimeError('已安装启动器的目标不是此 Codex 应用包')
    with locked():
        current = status()
        if current.get('available') and Path(current['source']) == source:
            state = read_state()
            state['enabled'] = True
            state['original_command'] = config['app_command']
            write_json(state_path(), state)
            return status()['reason']
        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            raise RuntimeError('需要在图形桌面会话中进行副本启动与 Appearance 验收')
        versions = root_path() / 'versions'
        versions.mkdir(parents=True, exist_ok=True)
        size = sum(p.stat().st_size for p in source.rglob('*') if p.is_file())
        if shutil.disk_usage(versions).free < size + 2 * archive_path.stat().st_size + 200 * 1024 * 1024:
            raise RuntimeError('磁盘空间不足：需要完整应用副本、临时 ASAR 和测试空间')
        stage = Path(tempfile.mkdtemp(prefix=SUPPORTED_VERSION + '-staging-', dir=versions))
        evidence = root_path() / 'evidence' / stage.name
        try:
            # cp reflink is copy-on-write; never use hard links.
            subprocess.run(['cp', '-a', '--reflink=auto', '--no-preserve=ownership', str(source) + '/.', str(stage)], check=True)
            if digest_file(stage / 'resources/app.asar') != SUPPORTED_SHA256:
                raise RuntimeError('复制后的应用包校验失败')
            probe(stage, 'raw', evidence)
            archive = Archive(stage / 'resources/app.asar')
            new = stage / 'resources/app.asar.patched'
            changes = patch_changes(archive, data_path() / 'manage.py')
            rewritten = archive.rewrite(new, changes)
            for member, expected in changes.items():
                if rewritten.read(member) != expected:
                    raise RuntimeError('补丁写入校验失败：' + member)
            rewritten.verify()
            new.replace(stage / 'resources/app.asar')
            probe(stage, 'patched', evidence)
            if fingerprint(archive_path) != expected_source or fingerprint(source / 'ChatGPT') != expected_binary:
                raise RuntimeError('测试期间系统应用发生变化，未激活副本')
            final = versions / (SUPPORTED_VERSION + '-' + stage.name.rsplit('-', 1)[-1])
            stage.rename(final)
            state = {'schema_version': 1, 'enabled': True, 'validated': True,
                     'adapter_hash': adapter_hash(),
                     'version': SUPPORTED_VERSION, 'source': str(source), 'copy': str(final),
                     'source_sha256': SUPPORTED_SHA256, 'source_fingerprint': expected_source,
                     'binary_fingerprint': expected_binary,
                     'copy_fingerprint': fingerprint(final / 'resources/app.asar'),
                     'copy_binary_fingerprint': fingerprint(final / 'ChatGPT'),
                     'original_command': config['app_command'], 'evidence': str(evidence)}
            write_json(state_path(), state)
            previous = Path(current['copy']) if current.get('copy') else None
            if previous and previous != final and not previous.is_symlink() and \
               previous.parent.resolve() == versions.resolve() and previous.exists() and not running_in(previous):
                # Activate first. Cleanup failure must not roll back a good install.
                try:
                    shutil.rmtree(previous)
                except OSError:
                    pass
            return f'原生 Appearance 副本已通过验收。{status()["reason"]}\n验收证据：{evidence}'
        except BaseException:
            if stage.exists() and not running_in(stage):
                shutil.rmtree(stage)
            raise


def disable():
    with locked():
        state = read_state()
        if state:
            state['enabled'] = False
            write_json(state_path(), state)
    return '原生集成已关闭；下次使用系统原版，动画功能仍保留。'


def uninstall():
    with locked():
        state = read_state()
        if state:
            state['enabled'] = False
            write_json(state_path(), state)
        versions = root_path() / 'versions'
        if versions.exists() and running_in(versions):
            return '已关闭原生集成；副本仍在运行，请正常退出 Codex 后再次 native uninstall。'
        if versions.exists():
            shutil.rmtree(versions)
        state_path().unlink(missing_ok=True)
    return '已移除应用副本，动画与配置保留。AppArmor 专用规则需按教程单独移除。'
