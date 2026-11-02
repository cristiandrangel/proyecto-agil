# Windows PowerShell 5.1+ / PowerShell 7. Run from a local NTFS checkout.
$ErrorActionPreference = 'Stop'
$actions = @($args)
if ($actions.Count -eq 0) { $actions = @('up') }
$repo = $PSScriptRoot
Set-Location -LiteralPath $repo
function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker failed (exit $LASTEXITCODE). See the diagnostic above." }
}
function Protect-PrivatePath([string] $path) {
    # Windows bind mounts do not expose useful POSIX mode bits. Enforce NTFS ACLs
    # on the host before allowing the Linux helper to read private delivery files.
    $acl = Get-Acl -LiteralPath $path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRuleSpecific($rule) }
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    if (Test-Path -LiteralPath $path -PathType Container) {
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
    } else {
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity,'FullControl','Allow')
    }
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $path -AclObject $acl
}
Invoke-Docker compose version
$info = (Invoke-Docker info --format '{{json .}}') | ConvertFrom-Json
if ($info.OSType -ne 'linux') { throw 'Switch Docker Desktop to Linux containers.' }
$endpoint = if ($env:DOCKER_CONTEXT) { Invoke-Docker context inspect $env:DOCKER_CONTEXT --format '{{.Endpoints.docker.Host}}' } elseif ($env:DOCKER_HOST) { $env:DOCKER_HOST } else { Invoke-Docker context inspect --format '{{.Endpoints.docker.Host}}' }
if ($endpoint -notmatch '^(npipe://|unix://)') { throw 'Use a local Docker Desktop context; remote daemons cannot bind this checkout.' }
if ($info.OperatingSystem -notmatch 'Docker Desktop') { throw 'This Windows launcher requires Docker Desktop with Linux containers. Use Bash for Linux Engine.' }
$socket = if ($env:EC2_DOCKER_SOCKET) { $env:EC2_DOCKER_SOCKET } else { '/var/run/docker.sock' }
$privateDir = Join-Path $repo '.local/ec2-emulation'
[void](New-Item -ItemType Directory -Force -Path $privateDir)
Protect-PrivatePath $privateDir
Get-ChildItem -LiteralPath $privateDir -Force -Recurse | ForEach-Object { Protect-PrivatePath $_.FullName }
for ($i = 0; $i -lt $actions.Count; $i++) {
    if ($actions[$i] -eq '--delivery-file') {
        if ($i + 1 -ge $actions.Count) { throw '--delivery-file requires a path inside this checkout.' }
        $hostFile = (Resolve-Path -LiteralPath $actions[$i + 1]).Path
        $prefix = $repo.TrimEnd('\') + '\'
        if (-not $hostFile.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Keep the private delivery file inside this checkout (normally .env.entrega).' }
        if ((Get-Item -LiteralPath $hostFile).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Delivery files must not be symlinks.' }
        Protect-PrivatePath $hostFile
        $actions[$i + 1] = '/workspace/' + $hostFile.Substring($prefix.Length).Replace('\','/')
    } elseif ($actions[$i].StartsWith('--delivery-file=')) {
        throw 'Pass --delivery-file and its path as separate arguments.'
    }
}
$network = 'agil-ec2-control'
& docker network inspect $network *> $null
if ($LASTEXITCODE -ne 0) {
    Invoke-Docker network create --label io.proyecto-agil.emulation=control $network
} else {
    $networkLabels = (Invoke-Docker network inspect --format '{{json .Labels}}' $network) | ConvertFrom-Json
    if ($networkLabels.'io.proyecto-agil.emulation' -ne 'control') {
        throw 'The network name agil-ec2-control belongs to another resource; nothing was changed.'
    }
}
Invoke-Docker build -t agil-ec2-runner:local -f infra/floci-runtime/Dockerfile.runner infra/floci-runtime
Invoke-Docker run --rm --network $network --env EC2_CONTROL_HOST=engine --env "EC2_CONTROL_NETWORK=$network" --env EC2_WINDOWS_ACL=checked --mount "type=bind,src=$repo,dst=/workspace" --mount "type=bind,src=$socket,dst=/var/run/docker.sock" --workdir /workspace agil-ec2-runner:local @actions
