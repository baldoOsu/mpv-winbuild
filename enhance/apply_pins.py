#!/usr/bin/env python3
"""Pin mpv-winbuild-cmake package sources to the commits listed in a pins TSV.

usage: python3 -I apply_pins.py <pins.tsv> <mpv-winbuild-cmake dir>

Rows: name<TAB>mode<TAB>value<TAB>note
  reset  add `GIT_RESET <sha>` to the package's ExternalProject_Add; `ninja update` resets the
         clone to it (only packages that update covers).
  tag    set `GIT_TAG <sha>`; ExternalProject checks it out at clone time (toolchain, and
         packages `ninja update` skips).
  rust   rustup default toolchain, e.g. nightly-2026-06-11.
Exits non-zero if any row can't be applied, so a missing package never builds unpinned.
"""
import re
import sys
from pathlib import Path


def find_block(root: Path, name: str):
    pat = re.compile(rf"^ExternalProject_Add\(\s*{re.escape(name)}\s*$", re.M)
    for f in sorted(root.glob("packages/*.cmake")) + sorted(root.glob("toolchain/**/*.cmake")):
        text = f.read_text()
        m = pat.search(text)
        if m:
            end = re.compile(r"^\)\s*$", re.M).search(text, m.end())
            return f, text, m.start(), end.start()
    return None, None, None, None


def main() -> int:
    pins, root = Path(sys.argv[1]), Path(sys.argv[2])
    errors = 0
    for line in pins.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, mode, value = line.split("\t")[:3]
        if mode == "rust":
            f = root / "toolchain/rustup.cmake"
            t = f.read_text()
            new = t.replace("--default-toolchain nightly ", f"--default-toolchain {value} ")
            if new == t:
                print(f"ERROR rustup: '--default-toolchain nightly ' not found in {f}")
                errors += 1
                continue
            f.write_text(new)
            print(f"rust      rustup -> {value}")
            continue
        f, text, start, end = find_block(root, name)
        if f is None:
            print(f"ERROR {name}: no ExternalProject_Add({name}) found")
            errors += 1
            continue
        block = text[start:end]
        repo = re.search(r"^(\s*)GIT_REPOSITORY\s+\S+.*$", block, re.M)
        if not repo:
            print(f"ERROR {name}: no GIT_REPOSITORY in {f}")
            errors += 1
            continue
        indent = repo.group(1)
        if mode == "reset":
            if re.search(r"^\s*GIT_RESET\s", block, re.M):
                print(f"ERROR {name}: already has GIT_RESET; drop it from the pins file")
                errors += 1
                continue
            block = block[:repo.end()] + f"\n{indent}GIT_RESET {value}" + block[repo.end():]
        elif mode == "tag":
            if re.search(r"^\s*GIT_TAG\s", block, re.M):
                block = re.sub(r"^(\s*GIT_TAG\s+)\S+", rf"\g<1>{value}", block, count=1, flags=re.M)
            else:
                block = block[:repo.end()] + f"\n{indent}GIT_TAG {value}" + block[repo.end():]
            # A sha checkout is a detached HEAD. With GIT_REMOTE_NAME set, force_rebuild_git()/cleanup()
            # generate reset_head.sh with `git reset --hard @{u}`, which fails on a detached HEAD (exit 128,
            # "HEAD does not point to a branch") in the post-install cleanup step. Without it the script
            # resets to HEAD, as for upstream's sha-pinned mpv.
            block = re.sub(r"^[ \t]*GIT_REMOTE_NAME[ \t]+\S+[ \t]*\n", "", block, flags=re.M)
        else:
            print(f"ERROR {name}: unknown mode {mode}")
            errors += 1
            continue
        f.write_text(text[:start] + block + text[end:])
        print(f"{mode:9} {name} -> {value[:12]} ({f.relative_to(root)})")
    print(f"apply_pins: {errors} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
