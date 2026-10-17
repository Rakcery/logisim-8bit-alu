#!/usr/bin/env python3
"""Create the initial v2 ALU.circ from the v1 file.

Keeps v1's header (library numbers, options, toolbar) and copies the v1
subcircuits that v2 reuses unchanged (same name, same port order). main
starts empty; it is drawn by hand. Run once; afterwards use gen_blocks.py,
which only replaces the scripted circuits.

Usage: python3 tools/bootstrap_v2.py v1/ALU.circ ALU.circ
"""
import sys
import xml.etree.ElementTree as ET

REUSED = ["HalfAdder", "FullAdder", "Select1bit", "Register4bit"]


def main(src, dst):
    tree = ET.parse(src)
    root = tree.getroot()
    circuits = {c.get("name"): c for c in root.findall("circuit")}
    for c in list(circuits.values()):
        root.remove(c)
    main_c = ET.SubElement(root, "circuit", name="main")
    for k, v in (("appearance", "logisim_evolution"), ("circuit", "main"),
                 ("circuitnamedboxfixedsize", "true"), ("simulationFrequency", "1.0")):
        ET.SubElement(main_c, "a", name=k, val=v)
    for name in REUSED:
        root.append(circuits[name])
    ET.indent(tree, space="  ")
    tree.write(dst, encoding="UTF-8", xml_declaration=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
