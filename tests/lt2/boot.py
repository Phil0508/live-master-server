# -*- coding: utf-8 -*-
"""부하 테스트용 서버 1개만 깨끗하게 띄운다. 포트를 실제로 잡은 PID 를 남긴다."""
import os, sys, subprocess, time, socket, json
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5177

# ⚠️ netstat 은 윈도우에만 있다. 맥에서도 작업하므로 갈라 둔다.
def owner_pid(port):
    if os.name == 'nt':
        out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True).stdout
        for ln in out.splitlines():
            # ⚠️ 서버는 0.0.0.0 에 붙는다. '127.0.0.1:포트' 로만 찾으면 영영 못 찾아서
            #    기동 실패로 오해하고, 죽이지도 못해 서버가 겹겹이 쌓인다.
            if ln.split()[1:2] and ln.split()[1].endswith(':%d' % port) and 'LISTENING' in ln:
                return int(ln.split()[-1])
        return None
    out = subprocess.run(['lsof', '-ti', 'tcp:%d' % port, '-sTCP:LISTEN'],
                         capture_output=True, text=True).stdout.strip()
    return int(out.splitlines()[0]) if out else None

for f in ('live_master.db', 'live_master.db-wal', 'live_master.db-shm', 'game_data.json'):
    p = os.path.join(HERE, f)
    if os.path.exists(p):
        os.remove(p)

env = dict(os.environ)
env.update({'HEADLESS': '1', 'PORT': str(PORT),
            'ADMIN_PASSWORD': 'lt-sandbox-pw', 'SESSION_SECRET': 'lt-sandbox-secret-0123456789',
            'SELF_PING': 'off', 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1'})
log = open(os.path.join(HERE, 'server_out.log'), 'w', encoding='utf-8', errors='replace')
p = subprocess.Popen([sys.executable, 'server.py'], cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)

for _ in range(120):
    time.sleep(0.5)
    if owner_pid(PORT):
        break
pid = owner_pid(PORT)
print(json.dumps({'spawned': p.pid, 'port_owner': pid, 'port': PORT}, ensure_ascii=False))
open(os.path.join(HERE, 'server.pid'), 'w').write(str(pid or p.pid))
