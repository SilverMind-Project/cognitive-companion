# Windows build PC: the companion Android shell (`ccwin`)

`frontend/android/` (the tablet and Google TV shell) cannot be built on the Linux dev
box: it is aarch64, and Google ships no linux-arm64 Android build tools. It is built,
linted, and tested on the household's Windows x86_64 PC instead, driven from Linux by
`scripts/ccwin` over SSH as the PC's non-admin `builduser` account. The two PowerShell
scripts here are the PC's half; `scripts/ccwin install-remote` copies them to
`C:\ccwin\bin`.

The PC setup itself (the `builduser` account, OpenSSH, the firewall rule, the SDK, the JDK,
the `C:\ccwin` layout) is shared with the other projects that use the PC and is
described once, in `windows-pc-unified-setup-and-cross-project-build-guide.md` at the
nanai workspace root (Parts 0 to 9). This page covers only what this repository adds.

## One-time setup on the dev box

1. `~/.ssh/config` has a `Host buildpc` entry (address, `User builduser`,
   `IdentityFile ~/.ssh/buildpc_ed25519`, `IdentitiesOnly yes`). Confirm the PC's host key
   on the PC itself the first time: `ssh-keygen -lf C:\ProgramData\ssh\ssh_host_ed25519_key.pub`.
2. `scripts/ccwin install-remote`, then `scripts/ccwin avd-setup` (installs the Google TV
   image and creates or repairs both AVDs; safe to repeat).
3. `scripts/ccwin doctor` should report the toolchain, WHPX acceleration, both AVDs, the
   lock state, and the synced commit.

## Everyday use

```bash
export CC_COMPANION_URL='https://nanai.khoofia.com/companion?kiosk=1'
scripts/ccwin sync              # web build + cap sync here; same commit on the PC
scripts/ccwin check             # companion-core tests, lint (warnings fail), debug APK
scripts/ccwin test-instrumented tablet   # live device tests on a wiped tablet AVD
scripts/ccwin test-instrumented tv       # the same on the Google TV AVD
scripts/ccwin fetch latest      # the run folder, into artifacts/ccwin/<run-id>/
```

`make check-android-remote` and `make check-android-live` run the same steps. Neither is
part of `make check` or `make check-all`, which must pass with the PC off.

`sync` builds the committed `HEAD`. With uncommitted work it refuses unless given
`--allow-dirty`, which builds a snapshot commit of the working tree (a private ref,
`refs/ccwin/build`; no branch, index, or stash changes). Every run folder carries
`sync-manifest.json` with the commit, its base, and whether it was a snapshot.

## How the PC is used

- **One SSH call is one job.** Windows OpenSSH kills every process a session started
  when the session ends, so nothing outlives a call: Gradle runs without a daemon, an
  emulator is booted, used, and killed inside `test-instrumented`, and the adb server
  is restarted each time. There is deliberately no `emulator start` that returns.
- **The owner comes first.** While `C:\ccwin\locks\in_use.flag` exists (or a desk helper
  on `127.0.0.1:17420` reports `in_use`), every job refuses with exit 73.
- **One job at a time.** `C:\ccwin\locks\runner.lock` is held open for the whole job, so a
  killed session releases it. A second job exits 74 at once, or waits up to
  `CCWIN_WAIT_SECONDS`.
- **A sleeping PC fails fast** (exit 75) instead of retrying.

Exit codes: 0 ok, 1 build or test failure, 64 usage, 69 a guided routine is live (live
tests refuse), 70 harness error, 73 PC in use, 74 runner lock held, 75 PC unreachable.

## The live device tests

The instrumented tests run the real page the household serves, in the real shell, on
a wiped emulator. They check, with no tap anywhere: the page may play audio; the
server's command reaches this screen's own socket and wakes it; the page starts
listening; the device closes the microphone itself when the lease ends; the page uses
its TV layout exactly on a TV; and the remote's D-pad moves focus.

They connect to the household server, so `test-instrumented`:

- refuses to start (exit 69) while any guided routine is summoning, active, waiting,
  escalated, or in caregiver takeover, checked with the caregiver key from `.env`
  (`CC_CAREGIVER_API_KEY`, or `CCWIN_GUARD_KEY`), which never leaves the dev box;
- registers the room-less test surface `ccwin-test-device` (never a delivery target);
- passes the dedicated test key (`CC_COMPANION_TEST_API_KEY` in `.env`, or
  `CCWIN_COMPANION_KEY`) to the PC on stdin, never on a command line. The key's role,
  `companion_test_device`, holds exactly a companion screen's tokens plus
  `companion_surfaces.test:execute`.

The backend must be deployed with `CC_COMPANION_TEST_API_KEY` set for these to pass.

## Physical tablets and Google TV devices

USB devices attached to the owner's desktop session may not be visible to `builduser`, so
use wireless debugging. On the device, enable Developer options, then Wireless
debugging, and pair once:

```bash
scripts/ccwin adb pair <device-ip>:<pair-port> <code>
scripts/ccwin adb connect <device-ip>:<port>     # remembered; reconnected on each call
scripts/ccwin test-instrumented --device <device-ip>:<port>
```

A dedicated appliance (factory reset, no accounts) can be made device owner, which
lets the shell grant itself the microphone and camera and pin itself:

```bash
scripts/ccwin adb install <path-to>/app-debug.apk
scripts/ccwin adb shell dpm set-device-owner com.silvermind.companion/.CompanionDeviceAdminReceiver
```
