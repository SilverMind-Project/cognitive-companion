<#
.SYNOPSIS
  Creates or repairs the companion shell's emulators on the Windows build PC.

.DESCRIPTION
  Run through `scripts/ccwin avd-setup` (as builduser, under the runner lock). Idempotent:
  a missing system image is installed, a missing AVD is created, and an existing AVD
  has only the hardware keys below rewritten, so its data survives.

    companion_tablet_api35    Pixel Tablet, API 35 Google APIs, with an emulated front
                          camera (the attention check needs one) and a microphone.
    companion_googletv_api36  Google TV 1080p, API 36 (the app's compile and target SDK),
                          D-pad and no touchscreen, so TV navigation is exercised as a
                          remote would.

  Google ships no x86_64 Google TV image below API 36 (API 34 has only 32-bit x86).
#>
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$sdk = $env:ANDROID_HOME
$avdHome = $env:ANDROID_AVD_HOME
if (-not $sdk -or -not $avdHome) { [Console]::Error.WriteLine('ERROR: ANDROID_HOME and ANDROID_AVD_HOME must be set'); exit 70 }
$sdkmanager = Join-Path $sdk 'cmdline-tools\latest\bin\sdkmanager.bat'
$avdmanager = Join-Path $sdk 'cmdline-tools\latest\bin\avdmanager.bat'

$avds = @(
    @{
        Name     = 'companion_tablet_api35'
        Package  = 'system-images;android-35;google_apis;x86_64'
        Device   = 'pixel_tablet'
        Hardware = [ordered]@{
            'hw.camera.front' = 'emulated'
            'hw.audioInput'   = 'yes'
            'hw.keyboard'     = 'yes'
            'hw.ramSize'      = '4096'
        }
    },
    @{
        Name     = 'companion_googletv_api36'
        Package  = 'system-images;android-36;google-tv;x86_64'
        Device   = 'tv_1080p'
        Hardware = [ordered]@{
            'hw.dPad'         = 'yes'
            'hw.touchScreen'  = 'no'
            'hw.audioInput'   = 'yes'
            'hw.camera.front' = 'none'
            'hw.keyboard'     = 'yes'
            'hw.ramSize'      = '4096'
        }
    }
)

function Invoke-Tool([string]$CommandLine) {
    & cmd.exe /d /s /c "`"$CommandLine 2>&1`"" | ForEach-Object { [Console]::Out.WriteLine($_) }
    return $LASTEXITCODE
}

function Set-AvdHardware([string]$ConfigPath, [System.Collections.IDictionary]$Hardware) {
    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path $ConfigPath) { $lines.AddRange([string[]](Get-Content $ConfigPath)) }
    foreach ($key in $Hardware.Keys) {
        $entry = "$key=$($Hardware[$key])"
        $index = -1
        for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -like "$key=*") { $index = $i; break } }
        if ($index -ge 0) { $lines[$index] = $entry } else { $lines.Add($entry) }
    }
    [System.IO.File]::WriteAllLines($ConfigPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
}

# The emulator finds an AVD only through <name>.ini in ANDROID_AVD_HOME. `avdmanager
# create avd -p <dir>` (as the Windows setup guide runs it) writes that pointer under
# the creating account's own profile instead, so an AVD made that way exists on disk but
# is invisible to builduser. Writing the pointer here makes every AVD bootable by builduser.
function Set-AvdPointer([string]$Name, [string]$Package, [string]$AvdDir) {
    $apiLevel = (($Package -split ';')[1]) -replace '^android-', ''
    $pointer = @(
        'avd.ini.encoding=UTF-8',
        "path=$AvdDir",
        "path.rel=avd\$Name.avd",
        "target=android-$apiLevel"
    )
    [System.IO.File]::WriteAllLines((Join-Path $avdHome "$Name.ini"), $pointer, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($avd in $avds) {
    $imageDir = Join-Path $sdk ('system-images\' + (($avd.Package -split ';')[1..3] -join '\'))
    if (-not (Test-Path (Join-Path $imageDir 'system.img'))) {
        [Console]::Out.WriteLine("installing $($avd.Package)")
        # Licences were accepted when the SDK was installed; `y` answers any new one.
        $code = Invoke-Tool "(for /l %i in (1,1,20) do @echo y) | `"$sdkmanager`" --sdk_root=`"$sdk`" `"$($avd.Package)`""
        if ($code -ne 0 -or -not (Test-Path (Join-Path $imageDir 'system.img'))) {
            [Console]::Error.WriteLine("ERROR: installing $($avd.Package) failed")
            exit 1
        }
    }

    $avdDir = Join-Path $avdHome "$($avd.Name).avd"
    if (-not (Test-Path (Join-Path $avdDir 'config.ini'))) {
        [Console]::Out.WriteLine("creating $($avd.Name)")
        $code = Invoke-Tool "echo no| `"$avdmanager`" create avd -n $($avd.Name) -k `"$($avd.Package)`" -d $($avd.Device) -p `"$avdDir`" --force"
        if ($code -ne 0) { [Console]::Error.WriteLine("ERROR: creating $($avd.Name) failed"); exit 1 }
    }
    Set-AvdHardware (Join-Path $avdDir 'config.ini') $avd.Hardware
    Set-AvdPointer $avd.Name $avd.Package $avdDir
    [Console]::Out.WriteLine("configured $($avd.Name) ($($avd.Package))")
}

# The emulator, not the files on disk, decides whether an AVD exists.
$listed = @(& cmd.exe /d /s /c "`"`"$(Join-Path $sdk 'emulator\emulator.exe')`" -list-avds 2>&1`"" | ForEach-Object { "$_".Trim() })
$missing = @($avds | Where-Object { $listed -notcontains $_.Name } | ForEach-Object { $_.Name })
if ($missing.Count -gt 0) {
    [Console]::Error.WriteLine("ERROR: the emulator does not list: $($missing -join ', ')")
    exit 1
}
[Console]::Out.WriteLine("ready: $(($avds | ForEach-Object { $_.Name }) -join ', ')")
exit 0
