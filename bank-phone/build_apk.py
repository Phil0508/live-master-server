# -*- coding: utf-8 -*-
"""🏦 엔젤 입금알림 APK 만들기 — Gradle 없이 안드로이드 SDK 도구만으로(aapt2 · javac · d8 · zipalign · apksigner).

    python bank-phone/build_apk.py            → D:/android-dev/out/엔젤입금알림-<판>.apk

도구 자리(ANDROID_DEV, 기본 D:/android-dev):
    jdk-17*/                       자바 17 (Adoptium Temurin)
    sdk/platforms/android-34/      android.jar
    sdk/build-tools/34.0.0/        aapt2 · d8 · zipalign · apksigner
    keys/                          서명 열쇠(처음 한 번 만든다 · 저장소에 안 올린다)
⚠️ C 드라이브가 빠듯해서 도구 · 결과물은 전부 D 드라이브에 둔다.
"""
import glob
import os
import re
import secrets
import shutil
import subprocess
import sys
import zipfile

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
DEV = os.environ.get('ANDROID_DEV') or 'D:/android-dev'
JDK = sorted(glob.glob(os.path.join(DEV, 'jdk-17*')))[-1]
SDK = os.path.join(DEV, 'sdk')
BT = os.path.join(SDK, 'build-tools', '34.0.0')
PLAT = os.path.join(SDK, 'platforms', 'android-34', 'android.jar')
OUT = os.path.join(DEV, 'out')
KEYS = os.path.join(DEV, 'keys')
WIN = os.name == 'nt'


def tool(name):
    for ext in (('.exe', '.bat', '') if WIN else ('',)):
        p = os.path.join(BT, name + ext)
        if os.path.exists(p):
            return p
    sys.exit('도구가 없어요: %s (SDK build-tools 34.0.0 을 먼저 까세요)' % name)


def run(cmd):
    env = dict(os.environ, JAVA_HOME=JDK, PATH=os.path.join(JDK, 'bin') + os.pathsep + os.environ.get('PATH', ''))
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print(' '.join(str(c) for c in cmd))
        print(r.stdout[-3000:], r.stderr[-3000:])
        sys.exit('실패: %s' % os.path.basename(str(cmd[0])))
    return r.stdout


def main():
    if not os.path.exists(PLAT):
        sys.exit('android.jar 가 없어요: ' + PLAT)
    manifest = open(os.path.join(HERE, 'AndroidManifest.xml'), encoding='utf-8').read()
    ver = re.search(r'android:versionName="([^"]+)"', manifest).group(1)
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, 'classes'))
    os.makedirs(os.path.join(OUT, 'dex'))

    print('① 묶음 뼈대(aapt2)')
    base = os.path.join(OUT, 'base.apk')
    run([tool('aapt2'), 'link', '-o', base, '--manifest', os.path.join(HERE, 'AndroidManifest.xml'),
         '-I', PLAT, '--min-sdk-version', '24', '--target-sdk-version', '34'])

    print('② 자바 → 클래스(javac)')
    srcs = sorted(glob.glob(os.path.join(HERE, 'src', '**', '*.java'), recursive=True))
    run([os.path.join(JDK, 'bin', 'javac'), '-encoding', 'UTF-8', '--release', '11', '-Xlint:-options',
         '-classpath', PLAT, '-d', os.path.join(OUT, 'classes')] + srcs)

    print('③ 클래스 → 안드로이드 실행 파일(d8)')
    classes = sorted(glob.glob(os.path.join(OUT, 'classes', '**', '*.class'), recursive=True))
    run([tool('d8'), '--release', '--min-api', '24', '--lib', PLAT, '--output', os.path.join(OUT, 'dex')] + classes)

    print('④ 묶기 · 정렬(zipalign)')
    unsigned = os.path.join(OUT, 'unsigned.apk')
    shutil.copy(base, unsigned)
    with zipfile.ZipFile(unsigned, 'a', zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(OUT, 'dex', 'classes.dex'), 'classes.dex')
    aligned = os.path.join(OUT, 'aligned.apk')
    run([tool('zipalign'), '-p', '-f', '4', unsigned, aligned])

    print('⑤ 서명(apksigner)')
    os.makedirs(KEYS, exist_ok=True)
    ks, pw_file = os.path.join(KEYS, 'bankphone.jks'), os.path.join(KEYS, 'pass.txt')
    if not os.path.exists(ks):
        pw = secrets.token_hex(16)
        open(pw_file, 'w', encoding='utf-8').write(pw)
        run([os.path.join(JDK, 'bin', 'keytool'), '-genkeypair', '-keystore', ks, '-storepass', pw, '-keypass', pw,
             '-alias', 'bankphone', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
             '-dname', 'CN=Angel Company, O=Angel Company, C=KR'])
        print('   서명 열쇠를 새로 만들었어요: ' + ks + ' (잃어버리면 다음 판을 덮어 깔 수 없어요 — 지우지 마세요)')
    final = os.path.join(OUT, '엔젤입금알림-%s.apk' % ver)
    run([tool('apksigner'), 'sign', '--ks', ks, '--ks-pass', 'file:' + pw_file, '--out', final, aligned])
    run([tool('apksigner'), 'verify', final])
    print('✓ 다 됐어요: %s (%.0f KB)' % (final, os.path.getsize(final) / 1024))
    # 📥 조종실에서 받게 — 저장소 bank-phone/dist 에 이름을 고정해 둔다(서버 /download/bankphone.apk 가 내려준다)
    dist = os.path.join(HERE, 'dist')
    os.makedirs(dist, exist_ok=True)
    shutil.copy(final, os.path.join(dist, 'angel-bankphone.apk'))
    open(os.path.join(dist, 'version.txt'), 'w', encoding='utf-8').write(ver + '\n')
    print('   조종실 받기용으로 복사: bank-phone/dist/angel-bankphone.apk (판 %s) — 커밋 · 올리면 조종실에 새 판이 떠요' % ver)


if __name__ == '__main__':
    main()
