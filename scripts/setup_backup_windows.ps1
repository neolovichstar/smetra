#requires -Version 5.1
<#
  Первичная безопасная настройка зашифрованных копий «сметры.» на Windows.
  Запускать на собственном компьютере. Приватный ключ НИКОГДА не отправляется
  в GitHub и не передаётся в CLI: туда попадает только публичный ключ.
  Понадобятся установленные age-keygen и GitHub CLI (gh).
#>
[CmdletBinding()]
param(
    [string]$Repository = 'neolovichstar/smetra'
)
$ErrorActionPreference = 'Stop'

foreach ($program in @('age-keygen', 'gh')) {
    if (-not (Get-Command $program -ErrorAction SilentlyContinue)) {
        throw "Не найдена программа $program. Установите её с официального сайта и повторите запуск."
    }
}
& gh auth status --hostname github.com
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Необходимо войти в GitHub. Откроется авторизация через браузер.'
    & gh auth login --hostname github.com --web
    if ($LASTEXITCODE -ne 0) { throw 'Авторизация GitHub не удалась.' }
}

$keyDir = Join-Path $env:USERPROFILE '.smetra\backup-recovery'
$keyPath = Join-Path $keyDir 'smetra-backup-identity.txt'
if (-not (Test-Path -LiteralPath $keyDir)) {
    New-Item -ItemType Directory -Path $keyDir -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $keyPath)) {
    Write-Host 'Генерирую приватный ключ на этом компьютере. Он не покинет компьютер.'
    & age-keygen -o $keyPath
    if ($LASTEXITCODE -ne 0) { throw 'Не получилось сгенерировать ключ.' }
} else {
    Write-Host 'Уже существующий приватный ключ сохранён. Перезапись запрещена.'
}

$recipient = (& age-keygen -y $keyPath | Select-Object -First 1).Trim()
if ($LASTEXITCODE -ne 0 -or $recipient -notmatch '^age1[023456789acdefghjklmnpqrstuvwxyz]+$') {
    throw 'Не удалось проверить публичный ключ шифрования.'
}

# Публичная часть безопасна для GitHub Actions variable.
$recipient | & gh variable set SMETRA_BACKUP_AGE_RECIPIENT -R $Repository
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить публичный ключ в GitHub.' }
Write-Host 'Публичный ключ шифрования настроен.'

Write-Host 'Нужен URL из Supabase > Connect > Session pooler (порт 5432).'
Write-Host 'Адрес вводится скрыто; в логи он не записывается.'
$secure = Read-Host 'Вставьте URL подключения к PostgreSQL' -AsSecureString
$handle = [IntPtr]::Zero
try {
    $handle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $url = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($handle)
    $parsed = $null
    if (-not [Uri]::TryCreate($url, [UriKind]::Absolute, [ref]$parsed)) {
        throw 'Неверный URL подключения.'
    }
    if ($parsed.Scheme -notin @('postgresql', 'postgres') -or $parsed.Port -ne 5432) {
        throw 'Требуется URL PostgreSQL session pooler на порту 5432 (не 6543).'
    }
    if ($url -notmatch '(?:\?|&)sslmode=') {
        if ($url.Contains('?')) { $url += '&sslmode=require' }
        else { $url += '?sslmode=require' }
    }
    # GitHub CLI шифрует секрет локально и принимает его по stdin, а не аргументом.
    $url | & gh secret set SMETRA_BACKUP_DATABASE_URL -R $Repository
    if ($LASTEXITCODE -ne 0) { throw 'GitHub отклонил установку секрета.' }
} finally {
    if ($handle -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($handle)
    }
    $url = $null
    if ($secure) { $secure.Dispose() }
}
Write-Host 'Секрет подключения к БД сохранён в GitHub Actions.'
# Включаем расписание только после успешной установки ключа и секрета.
'true' | & gh variable set SMETRA_BACKUP_ENABLED -R $Repository
if ($LASTEXITCODE -ne 0) { throw 'Не удалось включить ежедневное резервное копирование.' }
Write-Host 'Задание резервного копирования активировано.'
Write-Host "Приватный ключ находится в $keyPath"
Write-Host 'Сделайте офлайн-копию ключа. Если его потерять, архивы расшифровать нельзя.'
Write-Host 'После включения workflow в основной ветке запустите его вручную в GitHub Actions.'
