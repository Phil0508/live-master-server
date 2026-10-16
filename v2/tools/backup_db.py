# -*- coding: utf-8 -*-
"""💾 v2 장부(SQLite) 백업 — 서버가 켜져 있어도 안전하게 한 벌 떠 둔다(sqlite 의 backup 기능 — 쓰는 중인 장부도 깨지지 않는다).

⚠️ 옛 프로그램은 바깥 DB(Postgres)에 적어서 서버가 죽어도 기록이 남았다. v2 는 서버 안의 파일 하나다 —
   디스크가 망가지면 후원 장부가 통째로 사라진다. 그래서 매일 한 벌씩 뜨고(서버 안), 원하면 바깥(Supabase 보관소)에도 올린다.

쓰는 법
  python -m v2.tools.backup_db                       # v2/data/backups/lm2-YYYYMMDD-HHMM.db.gz 하나 · 최근 14벌만 남긴다
  python -m v2.tools.backup_db --upload              # 거기에 더해 Supabase 보관소(backups 버킷, 비공개)에도 올린다
  LM2_BACKUP_UPLOAD=1 python -m v2.tools.backup_db   # 같은 것 — 스위치는 환경변수로(매일 도는 livemaster-v2-backup 이 이걸 본다)
  python -m v2.tools.backup_db --keep 30 --db <장부 경로>
바깥 올리기(10-17)
  - 켜기: /etc/livemaster.env 에 LM2_BACKUP_UPLOAD=1 한 줄(기본은 꺼짐 — 서비스 파일이 0 으로 둔다). 서비스 파일은 안 고친다.
  - ⚠️ 먼저 Supabase 보관소(Storage)에 **backups 버킷을 비공개(Public 끔)** 로 만든다. 장부에는 후원자 이름 · 메시지가 있다.
    올리기 전에 버킷을 물어보고, 없으면 만들라고 · **공개면 안 올린다**(주소만 알면 누구나 받아 갈 수 있어서).
  - 올리기가 실패하면 끝 번호 1(서비스 '실패' — journalctl -u livemaster-v2-backup 에 까닭). 서버 안 백업은 그래도 남는다.
되살리기: 서버를 멈추고 → gunzip 한 파일을 v2/data/lm2.db 로 바꿔 놓고(옛 lm2.db-wal · -shm 은 지운다) → 서버를 켠다.
"""
import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.dirname(HERE)
BUCKET = 'backups'
UPLOAD_ENV = 'LM2_BACKUP_UPLOAD'


def upload_wanted():
    """환경변수 스위치 — 1 · on · true · yes 면 켠다. 없거나 0 이면 끈다(기본)."""
    return (os.environ.get(UPLOAD_ENV) or '').strip().lower() in ('1', 'on', 'true', 'yes')


def snapshot(db_path, out_dir):
    """장부 한 벌 → .db.gz. 돌려주는 값: 만든 파일 경로."""
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M', time.gmtime(time.time() + 9 * 3600))     # 이름은 한국 시각
    final = os.path.join(out_dir, 'lm2-%s.db.gz' % stamp)
    fd, tmp = tempfile.mkstemp(prefix='lm2bk_', suffix='.db', dir=out_dir)
    os.close(fd)
    try:
        src = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
        dst = sqlite3.connect(tmp)
        with dst:
            src.backup(dst)
        ok = dst.execute('PRAGMA integrity_check').fetchone()[0]
        n = dst.execute('SELECT COUNT(*) FROM donations').fetchone()[0]
        dst.close()
        src.close()
        if ok != 'ok':
            raise RuntimeError('백업본 검사 실패: %s' % ok)
        part = final + '.part'
        with open(tmp, 'rb') as f, gzip.open(part, 'wb', compresslevel=6) as g:
            shutil.copyfileobj(f, g)
        os.replace(part, final)            # 다 쓴 뒤에 이름을 바꾼다 — 반쯤 쓴 백업이 '최신' 으로 보이지 않게
        print('💾 백업 %s (후원 %d건 · %.1fKB)' % (os.path.basename(final), n, os.path.getsize(final) / 1024))
        return final
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def prune(out_dir, keep):
    files = sorted(f for f in os.listdir(out_dir) if f.startswith('lm2-') and f.endswith('.db.gz'))
    for f in files[:-keep] if keep > 0 else []:
        os.remove(os.path.join(out_dir, f))
    return max(0, len(files) - keep)


def check_bucket(url, key):
    """backups 버킷이 있고 **비공개** 인가 — 아니면 까닭을 담아 RuntimeError(올리지 않는다)."""
    import requests
    r = requests.get('%s/storage/v1/bucket/%s' % (url, BUCKET), timeout=20,
                     headers={'apikey': key, 'Authorization': 'Bearer ' + key})
    if r.status_code != 200:
        if r.status_code in (400, 404) and 'not found' in (r.text or '').lower():
            raise RuntimeError('보관소에 %s 버킷이 없어요 — Supabase → Storage 에서 이름 %s · Public 끔(비공개)으로 먼저 만들어 주세요'
                               '(서버 안 백업은 됐습니다)' % (BUCKET, BUCKET))
        raise RuntimeError('%s 버킷을 확인하지 못했습니다 %s: %s' % (BUCKET, r.status_code, (r.text or '')[:200]))
    try:
        info = r.json()
    except ValueError:
        info = None
    if not isinstance(info, dict) or info.get('public') is not False:
        raise RuntimeError('%s 버킷이 공개(Public)로 되어 있거나 확인이 안 돼 올리지 않았습니다 — 장부에는 후원자 이름 · 메시지가 있어요. '
                           'Supabase → Storage → %s → 설정에서 Public 을 끄고 다시 돌려 주세요(서버 안 백업은 됐습니다)' % (BUCKET, BUCKET))


def upload(path):
    """Supabase 보관소(비공개 backups 버킷)에 올린다 — 열쇠는 시그니처와 같은 곳에서 읽는다(화면에 안 찍는다)."""
    import requests
    from v2.server.domain.signatures import _supabase_config
    url, key = _supabase_config()
    if not url or not key:
        raise RuntimeError('Supabase 설정이 없어 바깥에 올리지 못했습니다(서버 안 백업은 됐습니다)')
    check_bucket(url, key)
    with open(path, 'rb') as f:
        r = requests.post('%s/storage/v1/object/%s/v2/%s' % (url, BUCKET, os.path.basename(path)), data=f, timeout=120,
                          headers={'apikey': key, 'Authorization': 'Bearer ' + key,
                                   'Content-Type': 'application/gzip', 'x-upsert': 'true'})
    if r.status_code not in (200, 201):
        raise RuntimeError('바깥 올리기 실패 %s: %s' % (r.status_code, r.text[:200]))
    print('☁️  보관소에 올렸습니다: %s/v2/%s' % (BUCKET, os.path.basename(path)))


def main(argv=None):
    ap = argparse.ArgumentParser(description='v2 장부 백업')
    ap.add_argument('--db', default=os.environ.get('LM2_DB') or os.path.join(V2, 'data', 'lm2.db'))
    ap.add_argument('--out', default=os.path.join(V2, 'data', 'backups'))
    ap.add_argument('--keep', type=int, default=14)
    ap.add_argument('--upload', action='store_true', help='Supabase 보관소에도 올린다(환경변수 %s=1 과 같다)' % UPLOAD_ENV)
    a = ap.parse_args(argv)
    a.upload = a.upload or upload_wanted()
    if not os.path.exists(a.db):
        print('장부가 없습니다: %s' % a.db)
        return 2
    path = snapshot(a.db, a.out)
    gone = prune(a.out, a.keep)
    if gone:
        print('🧹 오래된 백업 %d벌을 지웠습니다(최근 %d벌만 남김)' % (gone, a.keep))
    if a.upload:
        try:
            upload(path)
        except Exception as e:
            print('⚠️ %s' % e)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
