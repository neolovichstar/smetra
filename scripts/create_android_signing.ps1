Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$directory = Join-Path $env:USERPROFILE '.smetra\android'
$keystore = Join-Path $directory 'release.p12'
$certificate = Join-Path $directory 'release.cer'
$secretFile = Join-Path $directory 'password.dpapi'
$manifestFile = Join-Path $directory 'signing.json'
$alias = 'smetra_release'

if ((Test-Path -LiteralPath $keystore) -or (Test-Path -LiteralPath $secretFile) -or (Test-Path -LiteralPath $manifestFile)) {
    throw 'Android signing material already exists. Refusing to replace the release key.'
}
$keytool = (Get-Command keytool.exe -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$random = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($random)
$password = ([BitConverter]::ToString($random)).Replace('-', '')
$env:SMETRA_SIGNING_SETUP_PASSWORD = $password
try {
    & $keytool -genkeypair -noprompt -storetype PKCS12 -keystore $keystore -alias $alias `
        -keyalg RSA -keysize 4096 -sigalg SHA256withRSA -validity 10000 `
        -dname 'CN=Smetra, O=Smetra, C=RU' `
        -storepass:env SMETRA_SIGNING_SETUP_PASSWORD -keypass:env SMETRA_SIGNING_SETUP_PASSWORD
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $keystore -PathType Leaf)) { throw 'Could not create signing keystore.' }

    & $keytool -exportcert -keystore $keystore -alias $alias -file $certificate `
        -storepass:env SMETRA_SIGNING_SETUP_PASSWORD
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $certificate -PathType Leaf)) { throw 'Could not export signing certificate.' }
    $fingerprint = (Get-FileHash -LiteralPath $certificate -Algorithm SHA256).Hash

    $encrypted = ConvertTo-SecureString $password -AsPlainText -Force | ConvertFrom-SecureString
    Set-Content -LiteralPath $secretFile -Value $encrypted -Encoding Ascii -NoNewline
    @{
        storeFile = $keystore
        alias = $alias
        certificateSha256 = $fingerprint
        createdAt = (Get-Date).ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $manifestFile -Encoding UTF8
    Write-Output "Keystore: $keystore"
    Write-Output "Certificate SHA-256: $fingerprint"
    Write-Output "Recovery: back up the keystore and its password before publishing. The password.dpapi file works only under this Windows user account."
} finally {
    Remove-Item Env:SMETRA_SIGNING_SETUP_PASSWORD -ErrorAction SilentlyContinue
    $password = $null
    [Array]::Clear($random, 0, $random.Length)
}
