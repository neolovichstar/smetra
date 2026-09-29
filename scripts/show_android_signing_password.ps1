Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$secretFile = Join-Path $env:USERPROFILE '.smetra\android\password.dpapi'
if (-not (Test-Path -LiteralPath $secretFile -PathType Leaf)) { throw 'Local Android signing password was not found.' }
$secure = Get-Content -LiteralPath $secretFile -Raw | ConvertTo-SecureString
$handle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($handle) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($handle) }
