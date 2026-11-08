# CangjieNext Manifest

This repository holds the [repo](https://gerrit.googlesource.com/git-repo/) manifest
for the CangjieNext organization on GitHub. It orchestrates a multi-repo checkout
of the full Cangjie toolchain.

```
manifest
└── default.xml
└── cangjie
    └── cangjie.xml
```

## How it works

The `<remote fetch=".">` is **relative**: repo resolves every project URL against
the URL you pass to `repo init -u`. A single manifest therefore works for the
organization owner, fork developers, and CI, each with their own accounts:

```bash
# 1) Owner / core developer (SSH)
repo init -u git@github.com:CangjieNext/cangjie_manifest.git -b main
repo sync -c

# 2) Fork developer (replace <you>; fork ALL repos you work on first)
repo init -u git@github.com:<you>/cangjie_manifest.git -b main
repo sync -c
# HTTPS also works:
# repo init -u https://github.com/<you>/cangjie_manifest.git -b main

# 3) CI / read-only (HTTPS, no credentials needed for public repos)
repo init -u https://github.com/CangjieNext/cangjie_manifest.git -b main
repo sync -c
```

## Repository groups

| Group       | Projects                                                    | Synced by default |
|-------------|-------------------------------------------------------------|-------------------|
| `default`   | cangjie_compiler, cangjie_runtime, cangjie_tools, cangjie_test, cangjie_test_framework, cangjie_docs, cangjie_stdx, cangjie_build, cangjie_multiplatform_interop, cangjie_python_interop, cangjie_js_interop | yes |
| `llvm`      | llvm-project (pinned to the commit required by the compiler) | no  |
| `vscode`    | vscode_cangjie                                               | no  |
| `plugins`   | cangjie_debug_adapter, cangjie_deveco_plugins                | no  |

Optional groups carry the special `notdefault` marker, so a plain `repo sync`
only fetches the core repos.

## Building the compiler

`cangjie_compiler` expects LLVM at `cangjie_compiler/third_party/llvm-project`
(see its `third_party/README.md`). The manifest checks out the pinned LLVM
commit exactly there, so request both groups at init time:

```bash
repo init -u git@github.com:CangjieNext/cangjie_manifest.git -b main -g default,llvm
repo sync -c
```

Already initialized? Add groups without re-downloading everything:

```bash
repo init -g default,llvm     # persistent
repo sync -c
# or one-off:
repo sync -g llvm
```

Then follow the build guides in [`cangjie_build/docs`](https://github.com/CangjieNext/cangjie_build) (`docs/linux.md`, `docs/macos.md`, `docs/windows.md`, ...).

## Tips

- `repo forall -c '<command>'` runs a command in every checked-out repository.
- `repo start <branch> --all` creates a topic branch across all repos.
- `repo status`, `repo diff`, `repo upload` work across repos like their git
  counterparts.
- Install repo via `brew install repo` (macOS) or `apt-get install repo`
  (Debian/Ubuntu), or the one-line script at the
  [official README](https://gerrit.googlesource.com/git-repo/).
