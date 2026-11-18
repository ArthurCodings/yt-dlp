# CreatorKit 一键安装（Windows）
# 用法：powershell -ExecutionPolicy Bypass -File creatorkit\setup.ps1 [-Cpu]
#   -Cpu  没有 NVIDIA 显卡时使用，不安装 CUDA 运行库
param([switch]$Cpu)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not (Test-Path .venv)) {
    if ($uv) { uv venv --python 3.11 .venv } else { py -3.11 -m venv .venv }
}
$py = Join-Path $repo '.venv\Scripts\python.exe'
$extra = if ($Cpu) { 'asr' } else { 'cuda' }

if ($uv) {
    uv pip install --python $py -e ".[default,curl-cffi,deno]" -e "./creatorkit[$extra]"
} else {
    & $py -m pip install -U pip
    & $py -m pip install -e ".[default,curl-cffi,deno]" -e "./creatorkit[$extra]"
}

if (-not (Test-Path "$env:USERPROFILE\.creatorkit.toml")) {
    Copy-Item "$PSScriptRoot\creatorkit.example.toml" "$env:USERPROFILE\.creatorkit.toml"
    Write-Host "已生成配置文件：$env:USERPROFILE\.creatorkit.toml（请修改 output_dir）"
}

& (Join-Path $repo '.venv\Scripts\ck.exe') doctor
Write-Host "`n安装完成。用法：creatorkit\ck.cmd get <链接>"
