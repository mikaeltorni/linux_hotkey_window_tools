"""Require complete CLI preflight before a mandatory owner core can run."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='owner-preflight-') as directory:
    temporary = Path(directory)
    checkout = temporary / 'owner'
    checkout.mkdir()
    tracked = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files'], text=True).splitlines()
    for relative in tracked:
        source = ROOT / relative
        if source.is_file() and not source.is_symlink():
            destination = checkout / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    manifest = checkout / 'installer/components.sh'
    # Replace only the core operation inside this isolated fixture. The actual public
    # install.sh parser/routing remains unmodified and must never invoke this stub.
    with manifest.open('a') as output:
        output.write('''\n# Halt if the separately managed core runs during a rejected request.
# Parameters: none. Returns: ninety-one.
CORE_FUNCTION() { printf 'parameters=none\\n' >&2; printf 'core\\n' >> "$CORE_MARKER"; printf '91\\n' >&2; return 91; }
# Keep obsolete-state migration isolated from this routing test.
# Parameters: none. Returns: zero.
remove_legacy_speech_to_text_state() { printf 'parameters=none\\n0\\n' >&2; }
'''.replace('CORE_FUNCTION', 'install_extension_core'))
    home = temporary / 'home'
    home.mkdir()
    tools = temporary / 'tools'
    tools.mkdir()
    getent = tools / 'getent'
    getent.write_text('#!/bin/bash\nprintf "%s:x:%s:%s::%s:/bin/bash\\n" "$USER" "$(id -u)" "$(id -g)" "$HOME"\n')
    getent.chmod(0o755)
    marker = temporary / 'core'
    env = dict(PATH=str(tools)+':/usr/bin:/bin', HOME=str(home), USER=os.environ.get('USER', 'mk'),
               XDG_STATE_HOME=str(temporary/'state'), XDG_CACHE_HOME=str(temporary/'cache'), CORE_MARKER=str(marker))
    for arguments in (['--select', 'unknown'], ['--select'], ['--default', 'unexpected'],
                      ['--select', 'unknown', '--all'], ['--configure-component', 'unknown']):
        result = subprocess.run(['bash', str(checkout/'install.sh'), *arguments], cwd=checkout, env=env, text=True, capture_output=True, timeout=20)
        assert result.returncode == 2, (arguments, result.returncode, result.stdout, result.stderr)
        assert not marker.exists(), (arguments, marker.read_text() if marker.exists() else '')
    result = subprocess.run(['bash', str(checkout/'install.sh'), '--config', 'unused.json', '--list-components'], cwd=checkout, env=env, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0 and result.stdout, (result.stdout, result.stderr)
    assert not marker.exists()
print('PASS: owner rejects complete malformed requests and routes queries before mandatory core operations')
