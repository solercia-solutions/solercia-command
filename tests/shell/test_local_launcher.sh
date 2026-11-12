#!/bin/bash
# Pruebas sintéticas: no usan servicios ni el navegador real.
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export ROOT
python3 - <<'PY'
import os, pathlib, shutil, subprocess, tempfile
root = pathlib.Path(os.environ['ROOT'])
with tempfile.TemporaryDirectory(prefix='solercia launcher ') as directory:
    work = pathlib.Path(directory)
    app = work / 'app con espacios'
    (app / 'scripts').mkdir(parents=True)
    for relative in ['scripts/local-status.sh', 'Open Solercia Command.command']:
        source = root / relative
        assert source.exists(), f'Falta implementación: {relative}'
        shutil.copy2(source, app / relative)
    binpath = work / 'bin'
    binpath.mkdir()
    log = work / 'calls'
    for name in ['python3', 'dirname']:
        (binpath / name).symlink_to(shutil.which(name))
    (binpath / 'curl').write_text('''#!/usr/bin/env python3
import os, sys
with open(os.environ['CALLS'], 'a') as out: out.write('curl ' + repr(sys.argv[1:]) + '\\n')
a=sys.argv[1:]
assert a[0]=='-q' and a[a.index('--noproxy')+1]=='*'
assert '--location' not in a and '-L' not in a
for flag in ['--connect-timeout','--max-time','--max-filesize']: assert flag in a
url=a[-1]; mode=os.environ.get('CASE','ok')
if mode=='timeout': sys.exit(28)
code='301' if mode=='redirect' else '200'
body='<html>Aplicación</html>'
if url.endswith('/api/v1/health'):
 body='{"status":"ok","service":"solercia-pm"}'
 if mode=='identity': body='{"status":"ok","service":"otro"}'
 if mode=='malformed': body='{broken'
 if mode=='proxy' and ':4242/' in url: body='{}'
print(body+'\\n'+code, end='')
''')
    (binpath / 'open').write_text('#!/bin/bash\nprintf "open %s\\n" "$*" >> "$CALLS"\n')
    for name in ['docker','npm','launchctl','kill','alembic','gestion.sh']:
        (binpath / name).write_text('#!/bin/bash\nprintf "FORBIDDEN\\n" >> "$CALLS"\nexit 99\n')
    for file in binpath.iterdir():
        if not file.is_symlink(): file.chmod(0o755)
    env = dict(os.environ, PATH=str(binpath), CALLS=str(log))
    for key in ['SOLERCIA_FRONTEND_URL','SOLERCIA_BACKEND_URL']:
        env.pop(key, None)
    def run(case='ok', extra=None, launcher=True):
        log.write_text('')
        command = app / ('Open Solercia Command.command' if launcher else 'scripts/local-status.sh')
        result = subprocess.run(['/bin/bash', str(command)], env=dict(env, CASE=case, **(extra or {})), cwd=work, capture_output=True, text=True, timeout=20)
        calls=log.read_text()
        assert 'FORBIDDEN' not in calls
        return result, calls
    result,calls=run()
    assert result.returncode==0, result.stdout+result.stderr
    assert calls.count('curl ')==3 and calls.count('open ')==1, calls
    assert 'schema_0026=unknown' in result.stdout and 'runtime=unknown' in result.stdout
    assert 'false' in result.stdout and 'no confirma' in result.stdout
    result,calls=run(launcher=False)
    assert result.returncode==0 and 'open ' not in calls
    for case in ['timeout','redirect','identity','malformed','proxy']:
        result,calls=run(case)
        assert result.returncode!=0 and 'open ' not in calls, case
    for key in ['SOLERCIA_FRONTEND_URL','SOLERCIA_BACKEND_URL']:
        for bad in ['https://example.com','http://localhost@evil.test','http://127.0.0.1:0','http://localhost:65536','http://localhost:x','http://localhost/a','http://localhost?x','http://localhost#x','http://%6cocalhost','http://localhost.evil','http://127.1','http://localhost\\@evil','http://localhost//','']:
            result,calls=run(extra={key:bad})
            assert result.returncode!=0 and not calls, (key,bad,calls)
    for valid in ['http://localhost:4242/', 'http://[::1]:4242', 'https://127.0.0.1:4242']:
        result,calls=run(extra={'SOLERCIA_FRONTEND_URL':valid})
        assert result.returncode==0 and calls.count('open ')==1
    for dependency in ['curl','open','python3']:
        target=binpath/dependency
        target.rename(binpath/(dependency+'.hidden'))
        result,calls=run()
        assert result.returncode!=0 and 'open ' not in calls
        (binpath/(dependency+'.hidden')).rename(target)
    print('PASS: apertura existente, estados, URL locales, dependencias y barreras sin red real')
PY
