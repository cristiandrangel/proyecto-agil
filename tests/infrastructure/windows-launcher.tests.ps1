# Standalone regression tests: no Pester, Docker daemon, credentials or services needed.
# Run with Windows PowerShell 5.1 or PowerShell 7. Linux runs the pure path cases.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$launcher = Join-Path $repo 'emulate-ec2.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$function = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'ConvertTo-WorkspaceDeliveryPath'
}, $true)
if (-not $function) { throw 'Delivery path function is missing from the real launcher.' }
# Load only the actual pure function, without executing the launcher or mocking it.
Invoke-Expression $function.Extent.Text
$script:passed = 0
function Assert-Equal($actual, $expected, [string] $label) {
    if ($actual -cne $expected) { throw "$label expected <$expected>, got <$actual>." }
    $script:passed++
}
function Assert-Throws([scriptblock] $action, [string] $message) {
    $caught = $null
    try { & $action } catch { $caught = $_ }
    if (-not $caught -or $caught.Exception.Message -notlike "*$message*") {
        throw "Expected error containing <$message>, got <$caught>."
    }
    $script:passed++
}
$cases = @(
    @('C:\Demo', 'C:\Demo\.env.entrega', '/workspace/.env.entrega'),
    @('C:\Demo\', 'C:\Demo\.env.entrega', '/workspace/.env.entrega'),
    @('C:\Demo Folder', 'C:\Demo Folder\private folder\.env.entrega', '/workspace/private folder/.env.entrega'),
    @('C:\Demo', 'c:\dEmO\nested\.env.entrega', '/workspace/nested/.env.entrega'),
    @('C:\', 'C:\private\.env.entrega', '/workspace/private/.env.entrega'),
    @('\\server\share\Demo', '\\server\share\Demo\.env.entrega', '/workspace/.env.entrega')
)
foreach ($case in $cases) {
    Assert-Equal (ConvertTo-WorkspaceDeliveryPath $case[0] $case[1]) $case[2] 'Container delivery path'
}
foreach ($outside in @('C:\Demo-other\.env.entrega', 'C:\Other\.env.entrega', 'D:\Demo\.env.entrega', 'C:\Demo')) {
    Assert-Throws { ConvertTo-WorkspaceDeliveryPath 'C:\Demo' $outside } 'inside this checkout'
}
if ($env:OS -ne 'Windows_NT') {
    Write-Output "PASS: $script:passed pure Windows-path assertions; native Windows launcher/NTFS checks require Windows."
    return
}

# The complete launcher runs against real local paths and NTFS ACLs. The function
# below shadows docker in this PowerShell process, so no real Docker is invoked.
$script:fixture = Join-Path ([IO.Path]::GetTempPath()) ('agil launcher test ' + [guid]::NewGuid().ToString('N'))
$checkout = Join-Path $script:fixture 'checkout with spaces'
[void](New-Item -ItemType Directory -Path $checkout)
Copy-Item -LiteralPath $launcher -Destination (Join-Path $checkout 'emulate-ec2.ps1')
$rootDelivery = Join-Path $checkout '.env.entrega'
$nestedDir = Join-Path $checkout 'private folder'
[void](New-Item -ItemType Directory -Path $nestedDir)
$nestedDelivery = Join-Path $nestedDir '.env.entrega'
$sibling = Join-Path $script:fixture 'checkout with spaces-other'
[void](New-Item -ItemType Directory -Path $sibling)
$outsideDelivery = Join-Path $sibling '.env.entrega'
foreach ($file in @($rootDelivery, $nestedDelivery, $outsideDelivery)) {
    Set-Content -LiteralPath $file -Value '# synthetic fixture; no credentials'
}
$originalLocation = Get-Location
$savedEnvironment = @{}
foreach ($name in @('DOCKER_CONTEXT', 'DOCKER_HOST', 'EC2_DOCKER_SOCKET')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name)
    [Environment]::SetEnvironmentVariable($name, $null)
}
# Global state is deliberate: the launcher invokes the fake from a child script
# scope, where $script: would refer to the launcher rather than this test file.
$global:AgilLauncherTestDocker = @{
    Calls = (New-Object 'System.Collections.Generic.List[object]')
    Type = 'linux'
    OS = 'Docker Desktop'
    Endpoint = 'npipe:////./pipe/dockerDesktopLinuxEngine'
    Failure = ''
}
function docker {
    [void]$global:AgilLauncherTestDocker.Calls.Add(@($args))
    $global:LASTEXITCODE = 0
    if ($args[0] -eq $global:AgilLauncherTestDocker.Failure) { $global:LASTEXITCODE = 17; return }
    switch ($args[0]) {
        'compose' { 'Docker Compose version v2.fixture'; return }
        'info' { @{ OSType = $global:AgilLauncherTestDocker.Type; OperatingSystem = $global:AgilLauncherTestDocker.OS } | ConvertTo-Json -Compress; return }
        'context' { $global:AgilLauncherTestDocker.Endpoint; return }
        'network' {
            if ($args -contains '--format') { '{"io.proyecto-agil.emulation":"control"}' }
            return
        }
        'build' { return }
        'run' { return }
        default { throw "Unexpected fake Docker invocation: $args" }
    }
}
function Run-Launcher([string[]] $arguments) {
    $global:AgilLauncherTestDocker.Calls.Clear()
    & (Join-Path $checkout 'emulate-ec2.ps1') @arguments *> $null
}
function Get-RunArguments {
    $calls = @($global:AgilLauncherTestDocker.Calls | Where-Object { $_[0] -eq 'run' })
    Assert-Equal $calls.Count 1 'Exactly one runner invocation'
    return ,$calls[0]
}
function Assert-PrivateAcl([string] $path) {
    $acl = Get-Acl -LiteralPath $path
    Assert-Equal $acl.AreAccessRulesProtected $true 'Private ACL does not inherit'
    $rules = @($acl.Access)
    Assert-Equal $rules.Count 1 'Private ACL has one explicit owner rule'
    Assert-Equal $rules[0].IdentityReference.Value ([Security.Principal.WindowsIdentity]::GetCurrent().Name) 'Private ACL identity'
    Assert-Equal ([string]$rules[0].AccessControlType) 'Allow' 'Private ACL permits owner'
    Assert-Equal $rules[0].IsInherited $false 'Private ACL rule is explicit'
    Assert-Equal ([string]$rules[0].FileSystemRights) 'FullControl' 'Private ACL grants owner full control'
}
try {
    # Relative root-level path, absolute nested path, and space-preserving argv.
    Run-Launcher @('up', '--delivery-file', '.env.entrega', '--public')
    $run = Get-RunArguments
    Assert-Equal ($run[-4..-1] -join '|') 'up|--delivery-file|/workspace/.env.entrega|--public' 'Root delivery argv'
    Assert-Equal ($run -contains "type=bind,src=$checkout,dst=/workspace") $true 'Checkout mount stays one argument'
    Assert-Equal ($run -contains 'EC2_WINDOWS_ACL=checked') $true 'Runner receives ACL guard'
    Assert-PrivateAcl $rootDelivery
    Assert-PrivateAcl (Join-Path $checkout '.local/ec2-emulation')

    $env:EC2_DOCKER_SOCKET = '/custom/docker.sock'
    $env:DOCKER_CONTEXT = 'desktop-linux'
    Run-Launcher @('up', '--delivery-file', $nestedDelivery, '--public')
    $run = Get-RunArguments
    Assert-Equal ($run[-4..-1] -join '|') 'up|--delivery-file|/workspace/private folder/.env.entrega|--public' 'Nested delivery argv'
    Assert-Equal ($run -contains 'type=bind,src=/custom/docker.sock,dst=/var/run/docker.sock') $true 'Custom socket mount'
    $context = @($global:AgilLauncherTestDocker.Calls | Where-Object { $_[0] -eq 'context' })
    Assert-Equal ($context[0] -contains 'desktop-linux') $true 'Explicit Docker context inspected'
    Assert-PrivateAcl $nestedDelivery
    $env:DOCKER_CONTEXT = $null
    $env:EC2_DOCKER_SOCKET = $null

    Run-Launcher @()
    $run = Get-RunArguments
    Assert-Equal $run[-1] 'up' 'No action defaults to up'

    Assert-Throws { Run-Launcher @('up', '--delivery-file', $outsideDelivery) } 'inside this checkout'
    Assert-Equal (@($global:AgilLauncherTestDocker.Calls | Where-Object { $_[0] -in @('build', 'run') }).Count) 0 'Outside path rejected before build/run'
    Assert-Throws { Run-Launcher @('up', '--delivery-file=.env.entrega') } 'separate arguments'
    Assert-Throws { Run-Launcher @('up', '--delivery-file') } 'requires a path'
    Assert-Throws { Run-Launcher @('up', '--delivery-file', 'missing.env') } 'does not exist'

    $global:AgilLauncherTestDocker.Endpoint = 'tcp://remote.example.invalid:2376'
    Assert-Throws { Run-Launcher @('doctor') } 'local Docker Desktop context'
    Assert-Equal (@($global:AgilLauncherTestDocker.Calls | Where-Object { $_[0] -in @('build', 'run') }).Count) 0 'Remote context rejected before build/run'
    $global:AgilLauncherTestDocker.Endpoint = 'npipe:////./pipe/dockerDesktopLinuxEngine'
    $env:DOCKER_HOST = 'tcp://remote.example.invalid:2376'
    Assert-Throws { Run-Launcher @('doctor') } 'local Docker Desktop context'
    $env:DOCKER_HOST = $null
    $global:AgilLauncherTestDocker.Type = 'windows'
    Assert-Throws { Run-Launcher @('doctor') } 'Linux containers'
    $global:AgilLauncherTestDocker.Type = 'linux'
    $global:AgilLauncherTestDocker.OS = 'Docker Engine - Community'
    Assert-Throws { Run-Launcher @('doctor') } 'requires Docker Desktop'
    $global:AgilLauncherTestDocker.OS = 'Docker Desktop'
    $global:AgilLauncherTestDocker.Failure = 'build'
    Assert-Throws { Run-Launcher @('doctor') } 'Docker failed (exit 17)'
    Assert-Equal (@($global:AgilLauncherTestDocker.Calls | Where-Object { $_[0] -eq 'run' }).Count) 0 'Build failure never starts runner'
    Write-Output "PASS: $script:passed assertions, real Windows launcher and NTFS ACLs, fake Docker only."
} finally {
    Set-Location -LiteralPath $originalLocation.Path
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name])
    }
    Remove-Item Function:\docker
    Remove-Variable AgilLauncherTestDocker -Scope Global
    Remove-Item -LiteralPath $script:fixture -Force -Recurse
}
# Reset the intentionally failed fake Docker exit code only after all assertions
# and cleanup succeed. Any uncaught assertion or cleanup error still propagates.
$global:LASTEXITCODE = 0
