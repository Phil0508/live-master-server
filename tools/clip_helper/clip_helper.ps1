# ✂️ 쇼츠 클립 도우미 — 회사 컴퓨터(OBS 가 있는 곳)에서 방송하는 동안 켜 둔다.
#
# 하는 일
#   OBS 리플레이 버퍼가 녹화 폴더에 'Replay ....mp4' 를 떨구면, 그 파일을 고른 '클립 폴더' 로 옮기고
#   조종실에서 정한 이름 규칙대로 이름을 붙인다(예: 2026-10-01 21-14-50 밍밍 1,000,000원 VIP.mp4).
#   조종실에서 클립 제목을 고치면 옮겨 둔 파일 이름도 따라 바뀐다.
#
# 어떻게 맞추나
#   방송판이 OBS 저장을 확인하면 서버의 클립 목록에 '저장 시각' 을 적는다.
#   도우미는 서버 목록(/api/data, 로그인 필요 없음)을 3초마다 읽어 파일 시각과 20초 안으로 맞는 줄을 찾는다.
#
# ⚠️ 설치할 것 없음 — 윈도우 기본 PowerShell 로 돈다. 폴더 설정은 %APPDATA%\ShortsClip 에 남는다.
param([switch]$Reset)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Windows.Forms

$Server = '__SERVER__'
$Dir = Join-Path $env:APPDATA 'ShortsClip'
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$CfgPath = Join-Path $Dir 'config.json'
$MapPath = Join-Path $Dir 'moved.json'
$KST = [TimeSpan]::FromHours(9)
$Host.UI.RawUI.WindowTitle = '쇼츠 클립 도우미'

function Say($msg, $color) {
    $t = (Get-Date).ToString('HH:mm:ss')
    if ($color) { Write-Host "[$t] $msg" -ForegroundColor $color } else { Write-Host "[$t] $msg" }
}

function Pick-Folder($title, $start) {
    $d = New-Object System.Windows.Forms.FolderBrowserDialog
    $d.Description = $title
    $d.ShowNewFolderButton = $true
    if ($start -and (Test-Path -LiteralPath $start)) { $d.SelectedPath = $start }
    $top = New-Object System.Windows.Forms.Form
    $top.TopMost = $true
    $r = $d.ShowDialog($top)
    $top.Dispose()
    if ($r -ne [System.Windows.Forms.DialogResult]::OK) { return $null }
    return $d.SelectedPath
}

function Save-Json($path, $obj) {
    $json = $obj | ConvertTo-Json -Depth 6
    [IO.File]::WriteAllText($path, $json, (New-Object Text.UTF8Encoding($false)))
}
function Load-Json($path) {
    if (Test-Path -LiteralPath $path) {
        try { return ([IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) | ConvertFrom-Json) } catch {}
    }
    return $null
}

# ── ① 폴더 고르기 (처음 한 번 · 폴더 바꾸기로 다시) ──
$cfg = Load-Json $CfgPath
if ($Reset -or -not $cfg -or -not $cfg.watch -or -not $cfg.target) {
    Write-Host ''
    Write-Host '  ① OBS 가 녹화를 저장하는 폴더를 고르세요.' -ForegroundColor Yellow
    Write-Host '     (OBS 설정 → 출력 → 녹화 경로와 같은 곳. 리플레이도 처음엔 여기 저장돼요)'
    $w = Pick-Folder 'OBS 녹화 폴더 — 리플레이가 처음 저장되는 곳' ([Environment]::GetFolderPath('MyVideos'))
    if (-not $w) { Write-Host '  취소했어요.'; exit 1 }
    Write-Host '  ② 쇼츠 클립을 모을 폴더를 고르세요. (새 폴더도 만들 수 있어요)' -ForegroundColor Yellow
    $t = Pick-Folder '쇼츠 클립을 모을 폴더' $w
    if (-not $t) { Write-Host '  취소했어요.'; exit 1 }
    $cfg = [pscustomobject]@{ watch = $w; target = $t }
    Save-Json $CfgPath $cfg
}
if (-not (Test-Path -LiteralPath $cfg.target)) { New-Item -ItemType Directory -Force -Path $cfg.target | Out-Null }

# ── 옮긴 파일 기억 (이름을 나중에 고치면 따라 바꾼다) ──
$moved = @{}
$mj = Load-Json $MapPath
if ($mj) {
    foreach ($p in $mj.PSObject.Properties) {
        $moved[$p.Name] = @{ path = [string]$p.Value.path; ids = @($p.Value.ids | Where-Object { $_ }); t = [int64]$p.Value.t; seq = [int]$p.Value.seq }
    }
}
function Save-Map { Save-Json $MapPath $moved }

function Get-State {
    $r = Invoke-WebRequest -UseBasicParsing -Uri ($Server + '/api/data') -TimeoutSec 10
    $txt = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())   # 한글이 깨지지 않게 직접 UTF-8 로 읽는다
    return ($txt | ConvertFrom-Json)
}

function Clean-Name([string]$s) {
    $s = ($s -replace '[\\/:*?"<>|\r\n\t]', '_').Trim().TrimEnd('.')
    if ($s.Length -gt 120) { $s = $s.Substring(0, 120).Trim() }
    if (-not $s) { $s = '클립' }
    return $s
}

function Build-Name([string]$fmt, $entries, [int64]$tMs, [int]$seq) {
    $title = '클립'
    if ($entries -and $entries.Count -gt 0) {
        $e0 = $entries[0]
        $title = if ($e0.name) { [string]$e0.name } else { [string]$e0.label }
        if ($entries.Count -gt 1) { $title = "$title 외 $($entries.Count - 1)" }
    }
    $dt = [DateTimeOffset]::FromUnixTimeMilliseconds($tMs).ToOffset($KST).DateTime   # 방송은 한국 시각으로 적는다
    $n = $fmt.Replace('{날짜}', $dt.ToString('yyyy-MM-dd')).Replace('{시각}', $dt.ToString('HH-mm-ss'))
    $n = $n.Replace('{번호}', ('{0:D2}' -f $seq)).Replace('{제목}', $title)
    return (Clean-Name $n)
}

function Unique-Path([string]$dir, [string]$name, [string]$ext) {
    $p = Join-Path $dir ($name + $ext)
    $i = 2
    while (Test-Path -LiteralPath $p) { $p = Join-Path $dir ("$name ($i)" + $ext); $i++ }
    return $p
}

function Test-Free([string]$path) {
    try { $fs = [IO.File]::Open($path, 'Open', 'ReadWrite', 'None'); $fs.Close(); return $true } catch { return $false }
}

Write-Host ''
Write-Host '  ✂  쇼츠 클립 도우미' -ForegroundColor Cyan
Write-Host "     서버      : $Server"
Write-Host "     OBS 폴더  : $($cfg.watch)"
Write-Host "     클립 폴더 : $($cfg.target)"
Write-Host '     방송 동안 이 창을 켜 두세요. 닫으면 옮기기를 멈춥니다. (폴더 바꾸기: change_folders.bat)'
Write-Host ''

$failShown = $false
while ($true) {
    try { $st = Get-State; if ($failShown) { Say '서버 다시 연결됨' 'Green' }; $failShown = $false }
    catch {
        if (-not $failShown) { Say "서버에 못 붙어요 — 5초마다 다시 해요 ($($_.Exception.Message))" 'Red'; $failShown = $true }
        Start-Sleep -Seconds 5; continue
    }
    $clip = $st.clip
    $fmt = if ($clip -and $clip.name_fmt) { [string]$clip.name_fmt } else { '{날짜} {시각} {제목}' }
    $log = @(); if ($clip -and $clip.log) { $log = @($clip.log) }
    $skew = 0
    if ($st.server_time) { $skew = [int64]$st.server_time - [DateTimeOffset]::Now.ToUnixTimeMilliseconds() }

    # ── ② 새 리플레이 파일 → 클립 폴더로 ──
    try {
        $files = @(Get-ChildItem -LiteralPath $cfg.watch -File -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like 'Replay*' -and $_.Extension -match '^\.(mp4|mkv|mov|flv|ts|m4v)$' -and $_.LastWriteTime -gt (Get-Date).AddHours(-24)
        } | Sort-Object LastWriteTime)
        foreach ($f in $files) {
            if (-not (Test-Free $f.FullName)) { continue }              # OBS 가 아직 쓰는 중
            $tMs = ([DateTimeOffset]$f.LastWriteTime).ToUnixTimeMilliseconds() + $skew
            # ⚠️ 한 순간은 파일 하나에만 붙는다 — 이미 다른 파일에 붙은 줄은 뺀다(연달아 저장되면 겹쳐 붙었다).
            #    남은 줄 중 파일 시각에 가장 가까운 저장 한 번(저장 시각 2초 안 = 같은 저장)만 고른다.
            $used = @{}
            foreach ($mv in $moved.Values) { foreach ($i in @($mv.ids)) { if ($i) { $used[[string]$i] = $true } } }
            $near = @($log | Where-Object { $_.saved_at -and -not $used.ContainsKey([string]$_.id) -and [math]::Abs([int64]$_.saved_at - $tMs) -le 20000 } |
                      Sort-Object { [math]::Abs([int64]$_.saved_at - $tMs) })
            $hits = @()
            if ($near.Count) {
                $s0 = [int64]$near[0].saved_at
                $hits = @($near | Where-Object { [math]::Abs([int64]$_.saved_at - $s0) -le 2000 } | Sort-Object ts)
            }
            $age = ((Get-Date) - $f.LastWriteTime).TotalSeconds
            if ($hits.Count -eq 0 -and $age -lt 45) { continue }       # 서버에 '저장됨' 이 아직 안 왔다 — 조금 더 기다린다
            $day = [DateTimeOffset]::FromUnixTimeMilliseconds($tMs).ToOffset($KST).ToString('yyyy-MM-dd')
            $seq = 1 + @($moved.Values | Where-Object { [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$_.t).ToOffset($KST).ToString('yyyy-MM-dd') -eq $day }).Count
            # ⏱ 이름의 {시각} 은 '그 순간'(목록 줄 시각)으로 — 저장은 순간 90초 뒤라 파일 시각은 1분 30초 늦다
            $tName = if ($hits.Count) { [int64]$hits[0].ts } else { $tMs - 90000 }
            $name = Build-Name $fmt $hits $tName $seq
            $dest = Unique-Path $cfg.target $name $f.Extension
            Move-Item -LiteralPath $f.FullName -Destination $dest
            $key = if ($hits.Count) { [string]$hits[0].id } else { 'f' + $tMs + '_' + $f.Name.GetHashCode() }
            $moved[$key] = @{ path = $dest; ids = @($hits | ForEach-Object { [string]$_.id }); t = $tName; seq = $seq }
            Save-Map
            if ($hits.Count) { Say ("✂ 옮김: " + [IO.Path]::GetFileName($dest)) 'Green' }
            else { Say ("✂ 옮김(목록에 없는 순간): " + [IO.Path]::GetFileName($dest)) 'Yellow' }
        }
    } catch { Say "옮기다 멈춤: $($_.Exception.Message)" 'Red' }

    # ── ③ 조종실에서 제목이나 이름 규칙을 바꿨으면 파일 이름도 ──
    try {
        foreach ($k in @($moved.Keys)) {
            $m = $moved[$k]
            if (-not $m.ids -or $m.ids.Count -eq 0 -or -not (Test-Path -LiteralPath $m.path)) { continue }
            $ents = @($log | Where-Object { $m.ids -contains [string]$_.id } | Sort-Object ts)
            if ($ents.Count -eq 0) { continue }
            $want = Build-Name $fmt $ents $m.t $m.seq
            $cur = [IO.Path]::GetFileNameWithoutExtension($m.path)
            if ($cur -eq $want -or $cur.StartsWith($want + ' (')) { continue }
            $dest = Unique-Path (Split-Path -LiteralPath $m.path) $want ([IO.Path]::GetExtension($m.path))
            Rename-Item -LiteralPath $m.path -NewName (Split-Path -Leaf $dest)
            $m.path = $dest
            Save-Map
            Say ("✎ 이름 바꿈: " + [IO.Path]::GetFileName($dest)) 'Cyan'
        }
    } catch { Say "이름 바꾸다 멈춤: $($_.Exception.Message)" 'Red' }

    Start-Sleep -Seconds 3
}
