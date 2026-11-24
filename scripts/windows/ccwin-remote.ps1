<#
.SYNOPSIS
  The Windows half of scripts/ccwin: builds and tests the companion Android shell on the
  shared Windows build PC, as the non-admin builduser account, over SSH.

.DESCRIPTION
  Deployed to C:\ccwin\bin by `scripts/ccwin install-remote`; never run by hand from a
  desktop session. Every command is one SSH session, and Windows OpenSSH kills every
  process a session started when it ends (the session's job object). So nothing here
  outlives the call: Gradle runs without a daemon, an emulator is started and killed
  inside the command that needs it, and the adb server (with its device connections)
  is restarted per call, which is why device commands reconnect the recorded devices.

  Shared protocol with the other projects that use this PC (xrflight's buildpc):
    C:\ccwin\locks\in_use.flag   The owner is using the PC: refuse to start anything.
    C:\ccwin\locks\runner.lock   One job at a time. Held open (not merely present) for
                                 the whole job, so a killed session releases it.
    C:\ccwin\runs\<run-id>\      Everything a job produced; `ccwin fetch` copies it back.

  Output is plain text on stdout, errors on stderr, and the exit code is the contract:
    0 ok, 1 the job failed (build or test failure), 64 usage, 70 harness error,
    73 the PC is marked in use, 74 another job holds the runner lock.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('doctor', 'status', 'sync', 'gradle', 'test-instrumented', 'adb', 'avd-setup')]
    [string]$Command,
    [string]$RunId = '',
    [string]$Workspace = 'nanai',
    [string]$Repo = 'cognitive-companion',
    [string]$Commit = '',
    [string]$Tasks = '',
    [ValidateSet('', 'tablet', 'tv')]
    [string]$Avd = '',
    [string]$Device = '',
    [int]$WaitSeconds = 0,
    [int]$BootTimeoutSeconds = 420,
    [switch]$ReadSecrets,
    # adb arguments, NUL-separated then base64: passed as one value so that an adb
    # flag such as -s is never taken for one of this script's parameters.
    [string]$ArgsBase64 = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$builduserRoot = 'C:\ccwin'
$LockDir = Join-Path $builduserRoot 'locks'
$InUseFlag = Join-Path $LockDir 'in_use.flag'
$RunnerLock = Join-Path $LockDir 'runner.lock'
$RunsRoot = Join-Path $builduserRoot 'runs'
$StagingDir = Join-Path $builduserRoot "staging\$Workspace"
$RepoDir = Join-Path $builduserRoot "repos\$Workspace\$Repo"
$AndroidDir = Join-Path $RepoDir 'frontend\android'
$DevicesFile = Join-Path $builduserRoot '.android\ccwin-devices.txt'
$LatestFile = Join-Path $RunsRoot 'ccwin-latest.txt'
$DeskHelperStatus = 'http://127.0.0.1:17420/status'
$EmulatorPort = 5584
$EmulatorSerial = "emulator-$EmulatorPort"
$AvdNames = @{ tablet = 'companion_tablet_api35'; tv = 'companion_googletv_api36' }

$ExitJobFailed = 1
$ExitUsage = 64
$ExitHarness = 70
$ExitInUse = 73
$ExitLocked = 74

function Write-Err([string]$Message) { [Console]::Error.WriteLine($Message) }
function Write-Out([string]$Message) { [Console]::Out.WriteLine($Message) }

function Fail([int]$Code, [string]$Message) {
    Write-Err "ERROR: $Message"
    exit $Code
}

# -NoProfile skips builduser's profile, so the toolchain comes from machine scope: the
# Windows guide sets it there for every account. Reading it here (not hardcoding paths)
# means a moved SDK or JDK needs no change to this script.
function Initialize-Toolchain {
    foreach ($name in 'JAVA_HOME', 'ANDROID_HOME', 'ANDROID_AVD_HOME', 'GRADLE_USER_HOME') {
        $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
        if (-not $value) { Fail $ExitHarness "machine environment variable $name is not set (see the Windows setup guide, Part 6)" }
        Set-Item -Path "env:$name" -Value $value
    }
    $env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
    $env:ANDROID_USER_HOME = Join-Path $builduserRoot '.android'
    $env:TEMP = Join-Path $builduserRoot '.temp'
    $env:TMP = $env:TEMP
    $env:GIT_LFS_SKIP_SMUDGE = '1'
    $env:Path = @(
        (Join-Path $env:JAVA_HOME 'bin'),
        (Join-Path $env:ANDROID_HOME 'platform-tools'),
        (Join-Path $env:ANDROID_HOME 'emulator'),
        (Join-Path $env:ANDROID_HOME 'cmdline-tools\latest\bin'),
        [Environment]::GetEnvironmentVariable('Path', 'Machine')
    ) -join ';'
}

# Runs a native tool with stderr folded into stdout (Windows PowerShell 5.1 would
# otherwise wrap stderr lines as error records), streaming each line and, when given,
# appending it to a UTF-8 log. Returns the tool's exit code.
function Invoke-Native([string]$CommandLine, [string]$LogPath = '') {
    $writer = $null
    if ($LogPath) { $writer = New-Object System.IO.StreamWriter($LogPath, $true, (New-Object System.Text.UTF8Encoding($false))) }
    try {
        & cmd.exe /d /s /c "`"$CommandLine 2>&1`"" | ForEach-Object {
            [Console]::Out.WriteLine($_)
            if ($writer) { $writer.WriteLine($_) }
        }
        return $LASTEXITCODE
    } finally {
        if ($writer) { $writer.Dispose() }
    }
}

# Same as Invoke-Native but returns the output instead of streaming it.
function Get-NativeOutput([string]$CommandLine) {
    $lines = & cmd.exe /d /s /c "`"$CommandLine 2>&1`""
    return [pscustomobject]@{ Code = $LASTEXITCODE; Text = (($lines | ForEach-Object { "$_" }) -join "`n").Trim() }
}

function Test-OwnerInUse {
    if (Test-Path $InUseFlag) { return $true }
    # The desk helper (xrflight DT-08) is optional: absent or slow means "not in use",
    # so its absence can never block a job, and the flag file stays authoritative.
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 -Uri $DeskHelperStatus
        return [bool](($response.Content | ConvertFrom-Json).in_use)
    } catch {
        return $false
    }
}

function Assert-NotInUse {
    if (Test-OwnerInUse) { Fail $ExitInUse 'Windows PC is marked IN USE by owner; refusing to start job.' }
}

# The lock is an open handle, not a marker file: if the SSH session is killed the OS
# closes the handle and the next job proceeds, so a lock can never go stale. The file
# keeps the holder's JSON for `status`; readers may open it (FileShare.Read) but no
# second writer can.
function Enter-RunnerLock {
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ($true) {
        try {
            $stream = [System.IO.File]::Open($RunnerLock, 'OpenOrCreate', 'ReadWrite', 'Read')
            $holder = @{
                holder     = $Repo
                workspace  = $Workspace
                run_id     = $RunId
                command    = $Command
                started_at = (Get-Date).ToUniversalTime().ToString('o')
            } | ConvertTo-Json -Compress
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($holder)
            $stream.SetLength(0)
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush()
            return $stream
        } catch [System.IO.IOException] {
            if ((Get-Date) -ge $deadline) {
                Fail $ExitLocked "another job holds the runner lock: $(Get-LockHolder)"
            }
            Start-Sleep -Seconds 5
        }
    }
}

function Get-LockHolder {
    if (-not (Test-Path $RunnerLock)) { return 'none' }
    try {
        $reader = [System.IO.File]::Open($RunnerLock, 'Open', 'Read', 'ReadWrite')
        try {
            $text = (New-Object System.IO.StreamReader($reader)).ReadToEnd()
        } finally { $reader.Dispose() }
    } catch { return 'unreadable' }
    # A free lock still holds the last holder's JSON; only a failed exclusive open
    # means it is held now.
    try {
        $probe = [System.IO.File]::Open($RunnerLock, 'Open', 'ReadWrite', 'Read')
        $probe.Dispose()
        return "free (last: $text)"
    } catch [System.IO.IOException] {
        return "held: $text"
    }
}

function New-RunDir {
    if (-not $RunId) { Fail $ExitUsage 'missing -RunId' }
    if ($RunId -notmatch '^[A-Za-z0-9._-]+$') { Fail $ExitUsage "invalid run id '$RunId'" }
    $dir = Join-Path $RunsRoot $RunId
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Set-Content -Path $LatestFile -Value $RunId -Encoding ascii
    return $dir
}

function Assert-Synced {
    if (-not (Test-Path (Join-Path $AndroidDir 'gradlew.bat'))) {
        Fail $ExitHarness "no synced checkout at $RepoDir; run 'scripts/ccwin sync' first"
    }
}

# --- adb ----------------------------------------------------------------------------

# The adb server dies with each session, and with it every `adb connect`. Pairing
# survives (the shared adbkey), so reconnecting the recorded devices is enough.
function Connect-RecordedDevices {
    if (-not (Test-Path $DevicesFile)) { return }
    foreach ($target in Get-Content $DevicesFile) {
        $target = $target.Trim()
        if ($target) { $null = Get-NativeOutput "adb connect $target" }
    }
}

function Save-RecordedDevice([string]$Target) {
    $known = @()
    if (Test-Path $DevicesFile) { $known = @(Get-Content $DevicesFile | Where-Object { $_.Trim() }) }
    if ($known -notcontains $Target) {
        Add-Content -Path $DevicesFile -Value $Target -Encoding ascii
    }
}

# --- emulator -----------------------------------------------------------------------

function Start-Avd([string]$Name, [string]$RunDir) {
    $avdDir = Join-Path $env:ANDROID_AVD_HOME "$Name.avd"
    if (-not (Test-Path $avdDir)) { Fail $ExitHarness "AVD $Name not found; run 'scripts/ccwin avd-setup'" }
    $log = Join-Path $RunDir "emulator-$Name.log"
    # Headless and wiped: every run starts from the same device state, so a run never
    # depends on what an earlier one left behind (a stored key, a granted permission).
    $arguments = @(
        '-avd', $Name, '-port', $EmulatorPort, '-no-window', '-no-boot-anim',
        '-no-snapshot', '-wipe-data', '-gpu', 'swiftshader_indirect', '-camera-front', 'emulated'
    )
    $process = Start-Process -FilePath (Join-Path $env:ANDROID_HOME 'emulator\emulator.exe') `
        -ArgumentList $arguments -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
        -WindowStyle Hidden -PassThru
    Write-Out "emulator: started $Name (pid $($process.Id), serial $EmulatorSerial)"
    return $process
}

function Wait-AvdBoot([System.Diagnostics.Process]$Process) {
    $deadline = (Get-Date).AddSeconds($BootTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) { Fail $ExitJobFailed "emulator exited during boot (code $($Process.ExitCode)); see emulator log" }
        $boot = Get-NativeOutput "adb -s $EmulatorSerial shell getprop sys.boot_completed"
        if ($boot.Code -eq 0 -and $boot.Text -eq '1') {
            # Animations make instrumented UI checks flaky; a wiped device restores them.
            foreach ($setting in 'window_animation_scale', 'transition_animation_scale', 'animator_duration_scale') {
                $null = Get-NativeOutput "adb -s $EmulatorSerial shell settings put global $setting 0"
            }
            Write-Out 'emulator: boot completed'
            return
        }
        Start-Sleep -Seconds 5
    }
    Fail $ExitJobFailed "emulator did not finish booting in $BootTimeoutSeconds s"
}

function Stop-Avd([System.Diagnostics.Process]$Process) {
    if ($null -eq $Process) { return }
    $null = Get-NativeOutput "adb -s $EmulatorSerial emu kill"
    if (-not $Process.WaitForExit(30000)) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Out 'emulator: stopped'
}

# --- gradle -------------------------------------------------------------------------

function Invoke-Gradle([string]$TaskList, [string]$RunDir, [hashtable]$ExtraEnv = @{}) {
    $log = Join-Path $RunDir 'gradle.log'
    $saved = @{}
    foreach ($key in $ExtraEnv.Keys) {
        $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $ExtraEnv[$key], 'Process')
    }
    Push-Location $AndroidDir
    try {
        # No daemon: the session's job object would kill it anyway, and a daemon left
        # from another project's Gradle version would only cost memory.
        return Invoke-Native "gradlew.bat --no-daemon --console=plain $TaskList" $log
    } finally {
        Pop-Location
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
    }
}

# Copies every report and artifact a Gradle run may have produced, pass or fail, so a
# failure can be read on Linux after `ccwin fetch`.
function Save-GradleOutputs([string]$RunDir) {
    $manifest = Join-Path $StagingDir 'sync-manifest.json'
    if (Test-Path $manifest) { Copy-Item $manifest (Join-Path $RunDir 'sync-manifest.json') -Force }
    $sources = @{
        'app\build\reports'             = 'reports\app'
        'app\build\test-results'        = 'test-results\app'
        'app\build\outputs\apk'         = 'apk'
        'app\build\outputs\androidTest-results' = 'androidTest-results'
        'app\build\intermediates\lint_intermediate_text_report' = 'lint-text'
        'companion-core\build\reports'      = 'reports\companion-core'
        'companion-core\build\test-results' = 'test-results\companion-core'
    }
    foreach ($relative in $sources.Keys) {
        $from = Join-Path $AndroidDir $relative
        if (Test-Path $from) {
            $to = Join-Path $RunDir $sources[$relative]
            New-Item -ItemType Directory -Force -Path $to | Out-Null
            Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force
        }
    }
}

# --- commands -----------------------------------------------------------------------

function Invoke-Doctor {
    Initialize-Toolchain
    Write-Out "host=$(hostname) user=$(whoami) powershell=$($PSVersionTable.PSVersion)"
    foreach ($name in 'JAVA_HOME', 'ANDROID_HOME', 'ANDROID_AVD_HOME', 'GRADLE_USER_HOME') {
        $value = (Get-Item "env:$name").Value
        Write-Out ("{0}={1} exists={2}" -f $name, $value, (Test-Path $value))
    }
    $java = Get-NativeOutput 'java -version'
    Write-Out "java: $(($java.Text -split "`n")[0])"
    $adb = Get-NativeOutput 'adb version'
    Write-Out "adb: $(($adb.Text -split "`n")[0])"
    $git = Get-NativeOutput 'git --version'
    Write-Out "git: $($git.Text)"
    $accel = Get-NativeOutput 'emulator -accel-check'
    Write-Out "accel: $((($accel.Text -split "`n") | Where-Object { $_ -match 'usable|not' }) -join ' ')"
    foreach ($kind in $AvdNames.Keys | Sort-Object) {
        $avd = $AvdNames[$kind]
        Write-Out ("avd {0}={1} exists={2}" -f $kind, $avd, (Test-Path (Join-Path $env:ANDROID_AVD_HOME "$avd.avd")))
    }
    $drive = [System.IO.DriveInfo]::new('D')
    Write-Out ("disk D: free={0}GB" -f [int]($drive.AvailableFreeSpace / 1GB))
    Write-Out "in_use=$(Test-OwnerInUse)"
    Write-Out "runner_lock=$(Get-LockHolder)"
    $synced = 'none'
    if (Test-Path (Join-Path $RepoDir '.git')) {
        $head = Get-NativeOutput "git -C `"$RepoDir`" rev-parse HEAD"
        if ($head.Code -eq 0) { $synced = $head.Text }
    }
    Write-Out "synced_commit=$synced"
    Connect-RecordedDevices
    $devices = Get-NativeOutput 'adb devices'
    $attached = $devices.Text -split "`n" | Where-Object { $_ -match '^\S+\s+(device|offline|unauthorized)\b' }
    Write-Out "devices: $(if ($attached) { ($attached | ForEach-Object { $_.Trim() }) -join '; ' } else { 'none' })"
}

function Invoke-Status {
    Write-Out "in_use=$(Test-OwnerInUse)"
    Write-Out "runner_lock=$(Get-LockHolder)"
    if (Test-Path $LatestFile) { Write-Out "latest_run=$(Get-Content $LatestFile)" }
}

# Unpacks the bundle and the cap-sync outputs that `ccwin sync` staged, and checks out
# exactly the commit it built. Only frontend/android is checked out (sparse): Gradle
# needs nothing else, and it keeps the rest of the repository (and its Git LFS models)
# off the PC.
function Invoke-Sync {
    Initialize-Toolchain
    if ($Commit -notmatch '^[0-9a-f]{40}$') { Fail $ExitUsage "-Commit must be a full commit id (got '$Commit')" }
    $bundle = Join-Path $StagingDir 'repo.bundle'
    $deps = Join-Path $StagingDir 'cap-android-deps.tar.gz'
    foreach ($path in $bundle, $deps) { if (-not (Test-Path $path)) { Fail $ExitHarness "missing staged file $path" } }

    if (-not (Test-Path (Join-Path $RepoDir '.git'))) {
        New-Item -ItemType Directory -Force -Path $RepoDir | Out-Null
        if ((Invoke-Native "git -C `"$RepoDir`" init --quiet") -ne 0) { Fail $ExitHarness 'git init failed' }
        $null = Invoke-Native "git -C `"$RepoDir`" config core.longpaths true"
        $null = Invoke-Native "git -C `"$RepoDir`" sparse-checkout set --cone frontend/android"
    }
    if ((Invoke-Native "git -C `"$RepoDir`" fetch --quiet --force `"$bundle`" +refs/ccwin/build:refs/ccwin/build") -ne 0) {
        Fail $ExitHarness 'git fetch from the bundle failed'
    }
    if ((Invoke-Native "git -C `"$RepoDir`" checkout --quiet --force --detach $Commit") -ne 0) {
        Fail $ExitHarness "git checkout $Commit failed"
    }
    # Remove untracked, non-ignored leftovers; build outputs (ignored) stay for speed.
    $null = Invoke-Native "git -C `"$RepoDir`" clean -ffdq"

    # The generated cap-sync outputs are replaced wholesale, so one that a later sync no
    # longer produces cannot linger.
    $frontend = Join-Path $RepoDir 'frontend'
    foreach ($generated in 'android\capacitor-cordova-android-plugins', 'android\app\src\main\assets\public', 'node_modules\@capacitor') {
        $path = Join-Path $frontend $generated
        if (Test-Path $path) { Remove-Item -Recurse -Force $path }
    }
    if ((Invoke-Native "tar -xzf `"$deps`" -C `"$frontend`"") -ne 0) { Fail $ExitHarness 'extracting the cap-sync outputs failed' }
    $head = (Get-NativeOutput "git -C `"$RepoDir`" rev-parse HEAD").Text
    if ($head -ne $Commit) { Fail $ExitHarness "checkout is at $head, expected $Commit" }
    Write-Out "synced $Workspace/$Repo at $Commit"
}

function Invoke-GradleCommand {
    if (-not $Tasks) { Fail $ExitUsage 'missing -Tasks' }
    Initialize-Toolchain
    Assert-Synced
    $runDir = New-RunDir
    $code = Invoke-Gradle $Tasks $runDir
    Save-GradleOutputs $runDir
    Write-Out "run=$RunId gradle_exit=$code"
    if ($code -ne 0) { exit $ExitJobFailed }
}

# Secrets (the live test key) arrive on stdin as KEY=VALUE lines, never on a command
# line, and reach the test only as Gradle instrumentation arguments in this process's
# environment. They are not written to the run folder.
function Read-SecretArguments {
    $result = @{}
    if (-not $ReadSecrets) { return $result }
    while ($null -ne ($line = [Console]::In.ReadLine())) {
        if ($line -match '^([A-Za-z][A-Za-z0-9_]*)=(.*)$') {
            $result["ORG_GRADLE_PROJECT_android.testInstrumentationRunnerArguments.$($Matches[1])"] = $Matches[2]
        }
    }
    return $result
}

function Invoke-TestInstrumented {
    if (-not $Avd -and -not $Device) { Fail $ExitUsage 'give -Avd tablet|tv or -Device <serial>' }
    Initialize-Toolchain
    Assert-Synced
    $secrets = Read-SecretArguments
    $runDir = New-RunDir
    $emulator = $null
    $serial = $Device
    $code = $ExitJobFailed
    try {
        if ($Avd) {
            $emulator = Start-Avd $AvdNames[$Avd] $runDir
            $serial = $EmulatorSerial
            $null = Invoke-Native "adb -s $serial wait-for-device"
            Wait-AvdBoot $emulator
        } else {
            Connect-RecordedDevices
        }
        $null = Invoke-Native "adb -s $serial logcat -c"
        $secrets['ANDROID_SERIAL'] = $serial
        $code = Invoke-Gradle "$Tasks" $runDir $secrets
        $null = Invoke-Native "adb -s $serial logcat -d -v threadtime" (Join-Path $runDir 'logcat.txt')
    } finally {
        Save-GradleOutputs $runDir
        Stop-Avd $emulator
    }
    Write-Out "run=$RunId target=$serial gradle_exit=$code"
    if ($code -ne 0) { exit $ExitJobFailed }
}

function Invoke-Adb {
    $Rest = @()
    if ($ArgsBase64) {
        $decoded = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($ArgsBase64))
        $Rest = @($decoded.TrimEnd([char]0) -split [char]0)
    }
    if ($Rest.Count -eq 0) { Fail $ExitUsage 'missing adb arguments' }
    Initialize-Toolchain
    if ($Rest[0] -eq 'connect' -and $Rest.Count -ge 2) { Save-RecordedDevice $Rest[1] }
    if ($Rest[0] -eq 'disconnect' -and $Rest.Count -ge 2 -and (Test-Path $DevicesFile)) {
        $keep = @(Get-Content $DevicesFile | Where-Object { $_.Trim() -and $_.Trim() -ne $Rest[1] })
        Set-Content -Path $DevicesFile -Value $keep -Encoding ascii
    }
    Connect-RecordedDevices
    $quoted = ($Rest | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' '
    exit (Invoke-Native "adb $quoted")
}

function Invoke-AvdSetup {
    Initialize-Toolchain
    & (Join-Path $PSScriptRoot 'avd-setup.ps1')
    exit $LASTEXITCODE
}

# --- dispatch -----------------------------------------------------------------------

New-Item -ItemType Directory -Force -Path $LockDir, $RunsRoot, $StagingDir | Out-Null
switch ($Command) {
    'doctor' { Invoke-Doctor; exit 0 }
    'status' { Invoke-Status; exit 0 }
}

# Everything below starts work on the PC: respect the owner, then take the lock for the
# rest of this session.
Assert-NotInUse
$lock = Enter-RunnerLock
try {
    switch ($Command) {
        'sync' { Invoke-Sync }
        'gradle' { Invoke-GradleCommand }
        'test-instrumented' { Invoke-TestInstrumented }
        'adb' { Invoke-Adb }
        'avd-setup' { Invoke-AvdSetup }
    }
} catch {
    Write-Err "ERROR: $($_.Exception.Message)"
    Write-Err $_.ScriptStackTrace
    exit $ExitHarness
} finally {
    $lock.Dispose()
}
exit 0
