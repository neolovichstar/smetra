param(
    [string]$ApiBaseUrl = 'https://smetra.vercel.app'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$localSigning = Join-Path $env:USERPROFILE '.smetra\android'
$localManifest = Join-Path $localSigning 'signing.json'
if (-not $env:SIGNING_STORE_FILE -and (Test-Path -LiteralPath $localManifest -PathType Leaf)) {
    $saved = Get-Content -LiteralPath $localManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $protectedPassword = Get-Content -LiteralPath (Join-Path $localSigning 'password.dpapi') -Raw | ConvertTo-SecureString
    $handle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($protectedPassword)
    try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($handle) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($handle) }
    $env:SIGNING_STORE_FILE = $saved.storeFile
    $env:SIGNING_KEY_ALIAS = $saved.alias
    $env:SIGNING_STORE_PASSWORD = $password
    $env:SIGNING_KEY_PASSWORD = $password
    $env:RUSTORE_CERT_SHA256 = $saved.certificateSha256
    $password = $null
}
$required = @('SIGNING_STORE_FILE', 'SIGNING_STORE_PASSWORD', 'SIGNING_KEY_ALIAS', 'SIGNING_KEY_PASSWORD', 'RUSTORE_CERT_SHA256')
foreach ($name in $required) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Set $name in the local environment before building the release."
    }
}
$keystore = (Resolve-Path -LiteralPath $env:SIGNING_STORE_FILE -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $keystore -PathType Leaf)) { throw 'Signing keystore is not a file.' }
$env:SIGNING_STORE_FILE = $keystore

if ($ApiBaseUrl -ne 'https://smetra.vercel.app') {
    throw 'Production APK must use https://smetra.vercel.app.'
}
$sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } elseif ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
if (-not (Test-Path -LiteralPath $sdk -PathType Container)) { throw 'Android SDK not found. Set ANDROID_HOME.' }
$env:ANDROID_HOME = (Resolve-Path -LiteralPath $sdk).Path
$tools = Get-ChildItem -LiteralPath (Join-Path $env:ANDROID_HOME 'build-tools') -Directory |
    Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1
if ($null -eq $tools) { throw 'Android SDK Build Tools not found.' }
$apksigner = Join-Path $tools.FullName 'apksigner.bat'
$aapt = Join-Path $tools.FullName 'aapt.exe'
if (-not (Test-Path -LiteralPath $apksigner) -or -not (Test-Path -LiteralPath $aapt)) { throw 'apksigner or aapt is missing from Android SDK Build Tools.' }

Push-Location $repo
try {
    & (Join-Path $repo 'apps\mobile\gradlew.bat') -p apps/mobile lintRelease assembleRelease "-PapiBaseUrl=$ApiBaseUrl" --no-daemon
    if ($LASTEXITCODE -ne 0) { throw 'Release build or lint failed.' }

    $apk = Join-Path $repo 'apps\mobile\app\build\outputs\apk\release\app-release.apk'
    if (-not (Test-Path -LiteralPath $apk -PathType Leaf)) { throw 'Signed release APK was not produced.' }
    $badging = & $aapt dump badging $apk
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read APK manifest.' }
    $package = $badging | Where-Object { $_ -like 'package:*' } | Select-Object -First 1
    if ($package -notmatch "name='ru\.smetra\.mobile'" -or $package -notmatch "versionCode='10'" -or $package -notmatch "versionName='1\.6\.0'") {
        throw "Unexpected APK identity: $package"
    }
    $signature = & $apksigner verify --verbose --print-certs $apk 2>&1
    if ($LASTEXITCODE -ne 0) { throw "APK signature verification failed: $($signature -join ' ')" }
    $match = [regex]::Match(($signature -join "`n"), 'certificate SHA-256 digest:\s*([0-9a-fA-F]{64})')
    if (-not $match.Success) { throw 'Could not read the signing certificate fingerprint.' }
    $fingerprint = $match.Groups[1].Value.ToUpperInvariant()
    $expected = ($env:RUSTORE_CERT_SHA256 -replace '[^0-9a-fA-F]', '').ToUpperInvariant()
    if ($expected.Length -ne 64) { throw 'RUSTORE_CERT_SHA256 must contain a 64-digit SHA-256 fingerprint.' }
    if ($expected -ne $fingerprint) { throw 'Signing certificate differs from RUSTORE_CERT_SHA256. Do not publish this APK.' }

    $destination = Join-Path $repo 'dist\smetra-mobile-1.6.0-release.apk'
    New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
    Copy-Item -LiteralPath $apk -Destination $destination -Force
    Write-Output "APK: $destination"
    Write-Output "Package: $package"
    Write-Output "Certificate SHA-256: $fingerprint"
    Write-Output "File SHA-256: $((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash)"
} finally {
    Pop-Location
}
