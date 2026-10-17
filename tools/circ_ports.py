#!/usr/bin/env python3
"""Print the port order of every subcircuit in a Logisim Evolution .circ file.

With the default "logisim_evolution" appearance, inputs sit on the left and
outputs on the right of the subcircuit box, each side ordered by the pin's
(y, x) position inside the subcircuit. This order was cross-checked against
the instance wiring in the v1 file (main, ALUCore).

Usage: python3 circ_ports.py ALU.circ [CircuitName ...]
"""
import re
import sys
import xml.etree.ElementTree as ET


def ports(circuit):
    ins, outs = [], []
    for comp in circuit.findall("comp"):
        if comp.get("lib") != "0" or comp.get("name") != "Pin":
            continue
        a = {x.get("name"): x.get("val") for x in comp.findall("a")}
        x, y = map(int, re.findall(r"-?\d+", comp.get("loc")))
        entry = (y, x, a.get("label", "?"), int(a.get("width", "1")))
        (outs if a.get("type") == "output" else ins).append(entry)
    return sorted(ins), sorted(outs)


def main():
    root = ET.parse(sys.argv[1]).getroot()
    wanted = set(sys.argv[2:])
    for c in root.findall("circuit"):
        name = c.get("name")
        if wanted and name not in wanted:
            continue
        ins, outs = ports(c)
        fmt = lambda ps: ", ".join(f"{p[2]}[{p[3]}]" if p[3] > 1 else p[2] for p in ps)
        print(f"{name}\n  in : {fmt(ins)}\n  out: {fmt(outs)}")


if __name__ == "__main__":
    main()
