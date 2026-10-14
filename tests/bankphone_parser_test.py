# -*- coding: utf-8 -*-
"""📱 폰 앱(bank-phone)의 기업은행 알림 읽기 규칙 — Parser.java 를 컴퓨터 자바로 그대로 돌린다.

자바 11 이상(javac)이 있어야 한다. 찾는 순서: ANDROID_DEV/jdk-17* → JAVA_HOME → PATH. 없으면 건너뛴다.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(HERE, '..'))
APP = os.path.join(ROOT, 'bank-phone')


def find_jdk():
    dev = os.environ.get('ANDROID_DEV') or 'D:/android-dev'
    for d in sorted(glob.glob(os.path.join(dev, 'jdk-1[7-9]*')) + glob.glob(os.path.join(dev, 'jdk-2*')), reverse=True):
        if os.path.exists(os.path.join(d, 'bin', 'javac' + ('.exe' if os.name == 'nt' else ''))):
            return os.path.join(d, 'bin')
    jh = os.environ.get('JAVA_HOME')
    if jh and os.path.exists(os.path.join(jh, 'bin', 'javac' + ('.exe' if os.name == 'nt' else ''))):
        return os.path.join(jh, 'bin')
    j = shutil.which('javac')
    return os.path.dirname(j) if j else None


jdk = find_jdk()
if not jdk:
    print('javac(자바 11 이상)가 없어 건너뜁니다')
    print('통과 0 · 실패 0')
    sys.exit(0)
tmp = tempfile.mkdtemp(prefix='lmtest_bankphone_')
try:
    src = [os.path.join(APP, 'src', 'me', 'angelcompany', 'bankphone', 'Parser.java'), os.path.join(APP, 'test', 'ParserTest.java')]
    r = subprocess.run([os.path.join(jdk, 'javac'), '-encoding', 'UTF-8', '-d', tmp] + src, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        print('통과 0 · 실패 1')
        sys.exit(1)
    r = subprocess.run([os.path.join(jdk, 'java'), '-Dfile.encoding=UTF-8', '-Dstdout.encoding=UTF-8', '-cp', tmp, 'ParserTest'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(r.stdout)
    if r.returncode != 0 and '통과' not in r.stdout:
        print(r.stderr)
        print('통과 0 · 실패 1')
    sys.exit(r.returncode)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
