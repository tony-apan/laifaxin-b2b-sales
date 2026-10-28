import os
import pathlib
import subprocess
import shutil
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'tools/bootstrap.sh'

class BootstrapSafeMode(unittest.TestCase):
    def run_case(self, osname='Linux', uid='0', missing=True, fail=False, pm=True, mode='--install-noninteractive', brew=False, wsl=False, fail_ready=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bin = root / 'bin'
            bin.mkdir()
            log = root / 'calls'
            for name in ('sed', 'tr', 'cat', 'chmod'):
                (bin / name).symlink_to(shutil.which(name))
            (bin / 'bash').symlink_to('/bin/bash')
            def fake(name, body):
                path = bin / name
                path.write_text('#!/bin/bash\n' + body + '\n')
                path.chmod(0o755)
            fake('uname', 'if [ "$1" = -s ]; then echo "$FAKE_OS"; else echo x86_64; fi')
            fake('id', 'echo "$FAKE_UID"')
            fake('grep', 'exit 1')
            fake('awk', 'exit 0')
            fake('curl', 'exit 0')
            fake('sudo', 'echo sudo >> "$LOG"; exit 99')
            if not missing:
                fake('python3', 'echo Python 3.12.0')
                fake('git', 'exit 0')
            else:
                fake('git', 'exit 0')
            if pm:
                fake('apt-get', 'echo "apt-get $* frontend=$DEBIAN_FRONTEND" >> "$LOG"; if [ "$FAIL" = 1 ]; then exit 1; fi; if [ "$1" = install ]; then printf "#!/bin/bash\necho Python 3.12.0\n" > "$BIN/python3"; chmod +x "$BIN/python3"; fi')
            if brew:
                fake('brew', 'echo "brew $* noninteractive=$NONINTERACTIVE ci=$CI" >> "$LOG"; printf "#!/bin/bash\\necho Python 3.12.0\\n" > "$BIN/python3"; chmod +x "$BIN/python3"')
            if fail_ready:
                fake('apt-get', 'echo "apt-get $*" >> "$LOG"; if [ "$1" = install ]; then printf "#!/bin/bash\\necho Python 3.12.0\\n" > "$BIN/python3"; chmod +x "$BIN/python3"; exit 1; fi')
            env = {'PATH': str(bin), 'FAKE_OS': osname, 'FAKE_UID': uid, 'LOG': str(log), 'BIN': str(bin), 'FAIL': str(int(fail)), 'DEBIAN_FRONTEND': '', 'HOME': tmp}
            if wsl:
                env['WSL_DISTRO_NAME'] = 'test-wsl'
            result = subprocess.run(['/bin/bash', str(SCRIPT), mode], env=env, text=True, capture_output=True, timeout=10)
            calls = log.read_text() if log.exists() else ''
            return result, calls

    def test_macos_without_brew(self):
        r, calls = self.run_case(osname='Darwin')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('install_result=no_pm', r.stdout)
        self.assertEqual(calls, '')

    def test_git_bash_without_manager(self):
        r, calls = self.run_case(osname='MINGW64_NT', pm=False)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('install_result=no_pm', r.stdout)
        self.assertEqual(calls, '')

    def test_nonroot_rejected(self):
        r, calls = self.run_case(uid='501')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('install_result=privilege_required', r.stdout)
        self.assertEqual(calls, '')

    def test_root_install_and_recheck(self):
        r, calls = self.run_case()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('python_cmd=python3', r.stdout)
        self.assertIn('install_result=attempted', r.stdout)
        self.assertEqual(len(calls.splitlines()), 2, calls)
        self.assertIn('frontend=noninteractive', calls)
        self.assertNotIn('sudo', calls)

    def test_failure_rechecks_without_retry(self):
        r, calls = self.run_case(fail=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('install_result=failed', r.stdout)
        self.assertIn('python_cmd=none', r.stdout)
        self.assertEqual(len(calls.splitlines()), 1, calls)
        self.assertNotIn('sudo', calls)

    def test_no_missing_no_install(self):
        r, calls = self.run_case(missing=False, uid='501')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('install_result=nothing_to_do', r.stdout)
        self.assertEqual(calls, '')

    def test_brew_nonroot_success(self):
        r, calls = self.run_case(osname='Darwin', uid='501', brew=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('python_cmd=python3', r.stdout)
        self.assertIn('install_result=attempted', r.stdout)
        self.assertEqual(calls.strip(), 'brew install python3 noninteractive=1 ci=1')

    def test_wsl_nonroot_rejected(self):
        r, calls = self.run_case(osname='Linux', uid='501', wsl=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('os=wsl', r.stdout)
        self.assertIn('install_result=privilege_required', r.stdout)
        self.assertEqual(calls, '')

    def test_legacy_install_uses_fake_sudo(self):
        r, calls = self.run_case(uid='501', mode='--install')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('install_result=failed', r.stdout)
        self.assertEqual(calls.strip(), 'sudo')

    def test_failed_install_with_ready_dependencies(self):
        r, calls = self.run_case(fail_ready=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('install_result=failed', r.stdout)
        self.assertIn('all_ok=1', r.stdout)
        self.assertIn('python_cmd=python3', r.stdout)
        self.assertEqual(len(calls.splitlines()), 2)

    def test_unknown_argument_lists_all_modes(self):
        r, calls = self.run_case(mode='--unknown')
        self.assertEqual(r.returncode, 2)
        self.assertIn('只支持 --check-only / --install / --install-noninteractive', r.stdout)
        self.assertEqual(calls, '')

    def test_check_only(self):
        r, calls = self.run_case(mode='--check-only')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('install_result=not_attempted', r.stdout)
        self.assertEqual(calls, '')

if __name__ == '__main__':
    unittest.main()
