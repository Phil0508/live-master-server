# -*- coding: utf-8 -*-
"""
시그니처(로컬 signature.db + media) → Supabase (Storage + Postgres) 마이그레이션.
- 사진: 최대 1280px로 축소 + WebP(q82) 압축 (투명도 보존) → Storage 'media/images/{id}.webp'
- 사운드: 원본 그대로 → Storage 'media/sounds/{id}.{ext}'
- DB: signatures 테이블에 공개 URL과 함께 등록 (id 기준 upsert, 재실행 안전)

접속 정보는 SUPABASE_CREDENTIALS.txt(gitignore됨)에서 읽음. 코드에 비밀키 하드코딩 안 함.
사용:  python migrate_to_supabase.py            # 전체
       python migrate_to_supabase.py 2          # 앞 2개만 (테스트)
"""
import os, sys, io, sqlite3, mimetypes
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
import requests
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
SIG_DIR = os.path.join(BASE, '시그니처프로그램')
IMG_DIR = os.path.join(SIG_DIR, 'media', 'images')
SND_DIR = os.path.join(SIG_DIR, 'media', 'sounds')
DB_FILE = os.path.join(SIG_DIR, 'signature.db')
CREDS_FILE = os.path.join(BASE, 'SUPABASE_CREDENTIALS.txt')
BUCKET = 'media'
MAX_DIM = 1280
WEBP_Q = 82

def load_creds():
    creds = {}
    with open(CREDS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            creds[k.strip()] = v.split('#')[0].strip()
    return creds

CREDS = load_creds()
SUPABASE_URL = CREDS['SUPABASE_URL']
SECRET = CREDS['SUPABASE_SECRET_KEY']
DATABASE_URL = CREDS['DATABASE_URL']

# 1년 캐시 (Supabase 기본 1시간이면 오버레이 새로고침마다 전체를 다시 받아 전송량이 폭증한다)
MEDIA_CACHE_CONTROL = 'public, max-age=31536000, immutable'

def storage_upload(path, data, content_type):
    endpoint = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}"
    r = requests.post(endpoint, data=data, headers={
        "apikey": SECRET,
        "Authorization": f"Bearer {SECRET}",
        "Content-Type": content_type,
        "Cache-Control": MEDIA_CACHE_CONTROL,
        "x-upsert": "true",
    }, timeout=120)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"upload {path} failed {r.status_code}: {r.text[:200]}")
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"

def compress_image(src_path):
    """이미지를 WebP 바이트로 압축. 투명도 보존, 최대 1280px."""
    im = Image.open(src_path)
    # 애니메이션/특수모드 정리
    if im.mode in ('P', 'LA'):
        im = im.convert('RGBA')
    elif im.mode == 'CMYK':
        im = im.convert('RGB')
    w, h = im.size
    scale = min(1.0, MAX_DIM / max(w, h))
    if scale < 1.0:
        im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format='WEBP', quality=WEBP_Q, method=6)
    return buf.getvalue()

def ensure_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS signatures (
            id BIGINT PRIMARY KEY,
            amount INTEGER NOT NULL,
            title TEXT NOT NULL,
            image_url TEXT,
            sound_url TEXT,
            duration INTEGER DEFAULT 10,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_signatures_amount ON signatures(amount)")
    conn.commit()

def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=20)
    ensure_table(conn)
    cur = conn.cursor()

    sc = sqlite3.connect(DB_FILE)
    scur = sc.cursor()
    scur.execute("SELECT id, amount, title, image_file, sound_file, duration FROM signatures ORDER BY amount")
    rows = scur.fetchall()
    if limit:
        rows = rows[:limit]

    total = len(rows)
    up_img = up_snd = 0
    incomplete = []
    orig_bytes = new_bytes = 0

    for i, (sid, amount, title, img, snd, dur) in enumerate(rows, 1):
        image_url = sound_url = None
        # --- 이미지 ---
        if img:
            p = os.path.join(IMG_DIR, img)
            if os.path.exists(p):
                orig = os.path.getsize(p)
                data = compress_image(p)
                orig_bytes += orig; new_bytes += len(data)
                image_url = storage_upload(f"images/{sid}.webp", data, "image/webp")
                up_img += 1
        # --- 사운드 ---
        if snd:
            p = os.path.join(SND_DIR, snd)
            if os.path.exists(p):
                ext = snd.rsplit('.', 1)[-1].lower()
                ctype = 'audio/mpeg' if ext == 'mp3' else ('video/mp4' if ext == 'mp4' else mimetypes.guess_type(snd)[0] or 'application/octet-stream')
                with open(p, 'rb') as f:
                    data = f.read()
                sound_url = storage_upload(f"sounds/{sid}.{ext}", data, ctype)
                up_snd += 1

        if image_url is None or sound_url is None:
            incomplete.append((sid, amount, title, image_url is not None, sound_url is not None))

        cur.execute("""
            INSERT INTO signatures (id, amount, title, image_url, sound_url, duration)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              amount=EXCLUDED.amount, title=EXCLUDED.title,
              image_url=EXCLUDED.image_url, sound_url=EXCLUDED.sound_url, duration=EXCLUDED.duration
        """, (sid, amount, title, image_url, sound_url, dur or 10))
        conn.commit()
        print(f"[{i}/{total}] id={sid} amount={amount} '{title[:20]}' img={'O' if image_url else 'X'} snd={'O' if sound_url else 'X'}")

    print("\n========== 완료 ==========")
    print(f"DB 등록: {total}개 | 이미지 업로드: {up_img} | 사운드 업로드: {up_snd}")
    if orig_bytes:
        print(f"이미지 용량: {orig_bytes/1024/1024:.1f}MB → {new_bytes/1024/1024:.1f}MB ({new_bytes/orig_bytes*100:.0f}%)")
    if incomplete:
        print(f"\n⚠️ 불완전 {len(incomplete)}개 (파일 없어서 나중에 채워야 함):")
        for sid, amount, title, hi, hs in incomplete:
            miss = []
            if not hi: miss.append('이미지')
            if not hs: miss.append('사운드')
            print(f"   id={sid} {amount}원 '{title}' → {', '.join(miss)} 없음")
    conn.close(); sc.close()

if __name__ == '__main__':
    main()
