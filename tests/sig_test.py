# -*- coding: utf-8 -*-
"""시그니처 재생 경로 + 나가는 상태에 정체가 새지 않는지."""
import sys, json, urllib.request, urllib.error, time
sys.stdout.reconfigure(encoding='utf-8')
B='http://127.0.0.1:5199'; TOK='sandboxsecret123456'
ok=fail=0
def req(p,d=None,auth=True):
    if d is None and (p.startswith('/api/siggame/') or p.endswith('/next')): d={}
    body=json.dumps(d).encode() if d is not None else None
    h={'Content-Type':'application/json'}
    if auth: h['Authorization']='Bearer '+TOK
    r=urllib.request.Request(B+p,data=body,method='POST' if body is not None else 'GET',headers=h)
    try:
        with urllib.request.urlopen(r,timeout=10) as f: return f.status,json.loads(f.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read().decode())
        except Exception: return e.code,{}
def chk(label,cond,extra=''):
    global ok,fail
    if cond: ok+=1; print('  ✅ '+label)
    else: fail+=1; print('  ❌ '+label+'  '+str(extra))
def leaks(g):
    hid=[c for c in (g.get('cards') or []) if c.get('state')=='HIDDEN']
    return [c for c in hid if c.get('title') or c.get('image') or c.get('sig_id')], len(hid)

print('0) 판 준비')
s=req('/api/data')[1]; s['broadcast_active']=True; req('/api/data',s)
sigs=req('/api/signatures')[1]['signatures']
req('/api/siggame/clear')
req('/api/siggame/picks',{'picks':[x['id'] for x in sigs[:16]]})
req('/api/siggame/deal',{'minutes':10,'target':5})
req('/api/siggame/set',{'enabled':True})
req('/api/siggame/flip',{'id':1})
print('   16장 중 1장 뒤집은 상태')

print('\n1) 시그니처가 실제로 붙어서 재생 대기까지 가는가')
st,d=req('/api/donation',{'name':'홍길동','amount':12000,'message':'감사','tx_id':'sig_a1'})
chk('후원 접수', st==200, (st,d))
q=req('/api/data')[1].get('reaction_queue') or []
chk('리액션 큐에 1건 들어감', len(q)==1, len(q))
if q:
    it=q[0]
    # 큐 항목의 음원 열쇠는 audio_url 이다(시그니처 원본의 sound_url 을 옮겨 담는다)
    chk('재생에 필요한 것이 다 있다 (사진·음원·길이)',
        bool(it.get('image_url')) and bool(it.get('audio_url')) and it.get('duration'),
        {k:it.get(k) for k in ('title','image_url','audio_url','duration')})
    chk('후원자 이름이 붙어 있다', it.get('donator')=='홍길동', it.get('donator'))
chk('리액션 모드가 켜졌다', req('/api/data')[1].get('reaction_mode') is True)

print('\n2) 오버레이가 재생을 끝내고 넘길 때 (무인증)')
st,d=req('/api/reaction/next',{'id':q[0]['id']},auth=False)
chk('넘기기 성공', st==200, (st,d))
out=d.get('state') or {}
bad,hid=leaks(out.get('siggame') or {})
chk('덮인 카드 정체가 안 샌다', not bad, (len(bad),'/',hid, bad[:1]))
chk('picks 도 번호만',
    all(set(p)=={'sig_id'} for p in ((out.get('siggame') or {}).get('picks') or [])),
    ((out.get('siggame') or {}).get('picks') or [None])[0])
chk('대기함·장부는 안 나간다',
    all(k not in out for k in ('pending_donations','logs','bank_ledger','donation_history')),
    [k for k in ('pending_donations','logs','bank_ledger','donation_history') if k in out])
chk('관리자 토큰 없음', 'api_token' not in out)
chk('서버 시각은 온다', 'server_time' in out)
chk('큐가 비었고 리액션 모드도 꺼졌다',
    not (out.get('reaction_queue') or []) and out.get('reaction_mode') is False,
    (len(out.get('reaction_queue') or []), out.get('reaction_mode')))
chk('뒤집은 1번은 여전히 공개 상태',
    any(c.get('id')==1 and c.get('state')=='REVEALED' and c.get('image')
        for c in ((out.get('siggame') or {}).get('cards') or [])))

print('\n3) 번호 없이 큐를 지울 수 없다 (무인증)')
req('/api/donation',{'name':'테스터2','amount':13000,'message':'x','tx_id':'sig_a2'})
st,d=req('/api/reaction/next',{},auth=False)
chk('빈 요청은 400', st==400, (st,d))
chk('큐가 그대로 남아 있다', len(req('/api/data')[1].get('reaction_queue') or [])==1)
st,d=req('/api/reaction/next',{'id':'없는번호'},auth=False)
chk('엉뚱한 번호로는 안 지워진다',
    st==200 and len(req('/api/data')[1].get('reaction_queue') or [])==1, st)
st,d=req('/api/reaction/next',{})   # 로그인하면 번호 없이 건너뛰기 가능
chk('로그인하면 번호 없이 건너뛸 수 있다',
    st==200 and not (req('/api/data')[1].get('reaction_queue') or []), st)

print('\n4) 나가는 모든 경로에서 정체가 안 샌다')
req('/api/siggame/deal',{'minutes':10,'target':5}); req('/api/siggame/set',{'enabled':True})
req('/api/siggame/flip',{'id':2})
for name,(st,d) in [('/api/data (무인증)', req('/api/data',auth=False)),
                    ('/api/data (로그인)', req('/api/data'))]:
    bad,hid=leaks(d.get('siggame') or {})
    chk(name+' 덮인 카드 정체 안 샘', not bad, (len(bad),'/',hid))
    chk(name+' server_time 있음', 'server_time' in d)

print('\n5) 시그니처 등록·수정·삭제는 로그인 필요')
for p in ('/api/signatures/add','/api/signatures/update/1','/api/signatures/delete/1'):
    st,_=req(p,{},auth=False)
    chk(p+' → 401', st==401, st)

print('\n═══ 시그니처 경로 통과 %d / 실패 %d ═══' % (ok,fail))
