import sys
import re
import json
import base64
import urllib.request
import urllib.error
import psycopg2
import uuid
import os
import websocket

# 데이터베이스 연결 문자열
DB_URL = 'postgresql://my_postgres_db_jeaa_user:xL43VYSA3keTiELFls2VzflbiGsPeeKi@dpg-d92bdla8qa3s73d4hle0-a.oregon-postgres.render.com/my_postgres_db_jeaa'
UPLOAD_HOST = "https://toothcdn.xyz:8432/uploaded"

def main():
    # 1. 사용자로부터 투네이션 알림창 주소 입력받기
    if len(sys.argv) > 1:
        widget_url = sys.argv[1]
    else:
        print("="*60)
        print(" Toonation Asset Migration Tool ")
        print("="*60)
        widget_url = input("투네이션 알림창 주소를 입력해주세요: ").strip()

    if not widget_url:
        print("오류: 올바른 주소를 입력해야 합니다.")
        sys.exit(1)

    # URL에서 위젯 키값 추출
    # 예: https://toon.at/widget/alertbox/0ff7d51634720c364b007009dd564dff
    match = re.search(r'alertbox/([a-zA-Z0-9]{32})', widget_url)
    if not match:
        print("오류: 투네이션 알림창 URL 형식이 올바르지 않습니다.")
        print("예시: https://toon.at/widget/alertbox/0ff7d51634720c364b007009dd564dff")
        sys.exit(1)

    widget_key = match.group(1)
    print(f"\n[1] 알림창 키값 감지 완료: {widget_key}")
    
    # 2. 알림창 페이지 HTML 다운로드 및 payload 추출
    print(f"[2] 투네이션 웹페이지 로딩 중... ({widget_url})")
    req = urllib.request.Request(widget_url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8')
    except Exception as e:
        print(f"오류: 페이지 로딩 실패 - {e}")
        sys.exit(1)

    # HTML 내 window.payload 파싱
    payload_match = re.search(r'window\.payload\s*=\s*JSON\.parse\(\"(.*?)\"\);', html)
    if not payload_match:
        payload_match = re.search(r'window\.payload\s*=\s*JSON\.parse\((.*?)\);', html)

    if not payload_match:
        print("오류: 페이지에서 payload 설정 값을 찾을 수 없습니다.")
        sys.exit(1)

    raw_json_arg = payload_match.group(1)
    if raw_json_arg.startswith('"') and raw_json_arg.endswith('"'):
        try:
            raw_json_arg = json.loads(raw_json_arg)
        except:
            pass

    try:
        decoded_str = raw_json_arg.encode().decode('unicode-escape')
    except:
        decoded_str = raw_json_arg

    try:
        config_data = json.loads(decoded_str)
        payload = config_data.get('payload')
        uid = config_data.get('uid') or widget_key
    except Exception as e:
        print(f"오류: 설정 JSON 디코딩 실패 - {e}")
        sys.exit(1)

    if not payload:
        print("오류: JSON 데이터 내부에 payload 키가 존재하지 않습니다.")
        sys.exit(1)

    print(f"    - 연동 토큰(UID) 추출 완료: {uid}")
    print(f"    - 웹소켓 페이로드 추출 성공: {payload[:30]}...")

    # 3. 웹소켓을 통한 상세 설정 확보
    uri = f"wss://ws.toon.at/{payload}"
    print(f"[3] 투네이션 실시간 웹소켓 서버 접속 중... ({uri})")
    try:
        ws = websocket.WebSocket()
        ws.connect(uri, origin="https://toon.at")
        ws.settimeout(10.0)
        print("    - 대기열 설정 데이터 수신 대기...")
        msg = ws.recv()
        ws.close()
        
        ws_data = json.loads(msg)
        print("    - 설정 데이터 수신 완료!")
    except Exception as e:
        print(f"오류: 웹소켓 설정 획득 실패 - {e}")
        sys.exit(1)

    # 4. 데이터베이스 접속
    print(f"[4] 원격 PostgreSQL 데이터베이스 접속 중...")
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        print("    - 데이터베이스 연결 성공!")
    except Exception as e:
        print(f"오류: 데이터베이스 연결 실패 - {e}")
        sys.exit(1)

    # 중복 체크 및 데이터 다운로드/임포트 도우미 함수
    def download_file(url):
        print(f"      [Download] {url}")
        file_req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(file_req, timeout=15) as resp:
                return resp.read()
        except urllib.error.HTTPError as he:
            print(f"      [Error] Download Failed (HTTP {he.code}): {he.reason}")
            return None
        except Exception as ex:
            print(f"      [Error] Download Exception: {ex}")
            return None

    def import_item(title, amount, img_url=None, snd_url=None):
        # 중복체크
        cursor.execute("SELECT id FROM reaction_items WHERE title = %s AND amount = %s", (title, amount))
        if cursor.fetchone():
            print(f"    [건너뜀] '{title}' ({amount}원) - 이미 등록된 리액션이 존재합니다.")
            return

        print(f"    [*] 리액션 등록 시작: '{title}' ({amount}원)")
        
        img_id = None
        if img_url:
            img_data = download_file(img_url)
            if img_data:
                img_id = f"img_{uuid.uuid4().hex}"
                content_type = "image/gif" if ".gif" in img_url else "image/png"
                filename = os.path.basename(img_url).split('?')[0]
                cursor.execute(
                    "INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (%s, %s, %s, %s)",
                    (img_id, filename, content_type, psycopg2.Binary(img_data))
                )
                print(f"      => 이미지 저장 완료 ({len(img_data)} bytes) as {img_id}")
                
        snd_id = None
        if snd_url:
            snd_data = download_file(snd_url)
            if snd_data:
                snd_id = f"aud_{uuid.uuid4().hex}"
                content_type = "audio/mpeg" if ".mp3" in snd_url else "audio/wav"
                filename = os.path.basename(snd_url).split('?')[0]
                cursor.execute(
                    "INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (%s, %s, %s, %s)",
                    (snd_id, filename, content_type, psycopg2.Binary(snd_data))
                )
                print(f"      => 음원 저장 완료 ({len(snd_data)} bytes) as {snd_id}")

        cursor.execute(
            "INSERT INTO reaction_items (title, amount, audio_file_id, image_file_id) VALUES (%s, %s, %s, %s)",
            (title, amount, snd_id, img_id)
        )
        print(f"    [성공] '{title}' 리액션 등록이 완료되었습니다.")

    # 5. 파싱 및 가져오기 수행
    conf = ws_data.get('conf', {})
    
    # 5-1. 시그니처 사운드 가져오기
    conf_sig = conf.get('confSignature', {})
    signatures = conf_sig.get('Signatures', [])
    print(f"\n[5] 총 {len(signatures)}개의 시그니처 리소스 파싱 중...")
    
    imported_sigs = 0
    for sig in signatures:
        if sig.get('Enabled') == 1:
            name = sig.get('Name') or "시그니처"
            cash = sig.get('Cash') or 0
            h = sig.get('Hash')
            
            # 랜덤 시그니처 템플릿은 패스
            if name == "랜덤시그니처":
                continue
                
            img_url = None
            if sig.get('Thumbnail') == 1 and h:
                img_url = f"{UPLOAD_HOST}/__signature__/{h}.img"
                
            import_item(name, cash, img_url=img_url, snd_url=None)
            imported_sigs += 1
            
    print(f"    => 활성화된 시그니처 {imported_sigs}개 처리 완료.")

    # 5-2. 일반 리액션 항목 (item1, item2, item3) 가져오기
    donation = conf.get('donation', {})
    print("\n[6] 일반 후원 리액션 파싱 중...")
    
    imported_items = 0
    for key, val in donation.items():
        if key.startswith("item") and isinstance(val, dict):
            if val.get('enabled') == 1:
                cash = val.get('donation_min') or 0
                title = f"{cash}원 리액션"
                
                hash_img = val.get('hash_image')
                custom_img = val.get('customized_image')
                img_url = None
                if hash_img and (custom_img == 1 or custom_img is True):
                    img_url = f"{UPLOAD_HOST}/{uid}/{hash_img}.img"
                    
                hash_snd = val.get('hash_sound')
                custom_snd = val.get('customized_sound')
                ext_snd = val.get('customized_sound_ext', 'mp3')
                snd_url = None
                if hash_snd and (custom_snd == 1 or custom_snd is True):
                    snd_url = f"{UPLOAD_HOST}/{uid}/{hash_snd}.{ext_snd}"
                
                if img_url or snd_url:
                    import_item(title, cash, img_url=img_url, snd_url=snd_url)
                    imported_items += 1
                    
    print(f"    => 일반 리액션 {imported_items}개 처리 완료.")

    # 6. 트랜잭션 커밋 및 연결 종료
    conn.commit()
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print(" [성공] 투네이션 본계정 자산 마이그레이션이 완전히 성공했습니다! ")
    print("="*60)

if __name__ == "__main__":
    main()
