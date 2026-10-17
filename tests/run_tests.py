#!/usr/bin/env python3
"""Run every test vector in tests/vectors/ against ALU.circ with Logisim.

Combinational blocks use Logisim's own `--test-vector`. Files marked
"# sequential" use tools/probe/SeqTest.java, because Logisim 4.0.0 starts
each test-vector row from a reset state and can't test clocked blocks.

Exit code is non-zero if any vector fails or a run doesn't report results.

Usage: python3 tests/run_tests.py path/to/logisim-evolution.jar [ALU.circ] [Block ...]
"""
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "tests", "vectors")
PROBE = os.path.join(ROOT, "tools", "probe")


def java(args, jar):
    cmd = ["java"] + args
    if not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def run(block, path, circ, jar):
    with open(path) as f:
        sequential = "# sequential" in f.read(400)
    if sequential:
        src = os.path.join(PROBE, "SeqTest.java")
        cls = os.path.join(PROBE, "SeqTest.class")
        if not os.path.exists(cls) or os.path.getmtime(cls) < os.path.getmtime(src):
            subprocess.run(["javac", "-cp", jar, src], check=True)
        out = java(["-cp", f"{jar}{os.pathsep}{PROBE}", "SeqTest", circ, block, path], jar)
    else:
        out = java(["-jar", jar, "-w", block, path, circ], jar)
    m = re.search(r"Passed: (\d+), Failed: (\d+)", out)
    if not m:
        return False, "no result reported:\n" + out[-2000:]
    errors = "\n".join(l for l in out.splitlines() if l.startswith(("Error", "  ")))
    return m.group(2) == "0" and m.group(1) != "0", f"passed {m.group(1)}, failed {m.group(2)}\n{errors}"


def main():
    jar = os.path.abspath(sys.argv[1])
    circ = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(ROOT, "ALU.circ")
    only = set(sys.argv[3:])
    present = {c.get("name") for c in ET.parse(circ).getroot().findall("circuit")}
    ok_all = True
    for name in sorted(os.listdir(VECTORS)):
        block = name[:-4]
        if only and block not in only:
            continue
        if block not in present:
            print(f"SKIP {block}: not in {os.path.basename(circ)} yet (hand-drawn, still to come)")
            continue
        ok, msg = run(block, os.path.join(VECTORS, name), circ, jar)
        ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {block}: {msg.strip()}")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
