"""Small library for generating Logisim Evolution 4.0.0 subcircuits.

How it avoids guessing coordinates:
  1. A block is described as components plus named nets (no wires).
  2. The components are written to a temporary .circ and loaded by Logisim
     itself (tools/probe/Probe.java), which reports where every port really is.
  3. A Tunnel carrying the net name is dropped exactly on each connected port.
  4. The final file is probed again and checked: every net has >= 2 ports with
     one width, and no two component ports share a location by accident.

Only Tunnels connect things, so these blocks have no wires at all.
"""

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE_DIR = os.path.join(HERE, "probe")

# Library numbers used by the v1 file (kept identical in v2).
LIB_WIRING, LIB_GATES, LIB_MEMORY, LIB_IO, LIB_BASE = "0", "1", "4", "5", "8"

class Comp:
    """One component instance. `ports` maps a port key to the net name."""

    def __init__(self, lib, name, attrs, kind, height, width_px):
        self.lib, self.name, self.attrs, self.kind = lib, name, attrs, kind
        self.height, self.width_px = height, width_px
        self.loc = None
        self.ports = {}

    def to(self, port, net):
        self.ports[port] = net
        return self

    def to_many(self, prefix, nets):
        """Connect nets to ports prefix0, prefix1, ... in order."""
        for k, net in enumerate(nets):
            self.ports[f"{prefix}{k}"] = net
        return self


def gate(name, inputs=2):
    attrs = {"inputs": str(inputs)} if inputs != 2 and name != "NOT Gate" else {}
    h = max(60, inputs * 10 + 40)
    return Comp(LIB_GATES, name, attrs, "gate", h, 120)


def splitter(width):
    """end 0 = bus side, end k+1 = bit k (Logisim default bit mapping)."""
    return Comp(LIB_WIRING, "Splitter", {"fanout": str(width), "incoming": str(width)},
                "splitter", width * 10 + 40, 120)


def constant(width, value):
    attrs = {"value": hex(value)}
    if width != 1:
        attrs = {"width": str(width), **attrs}
    return Comp(LIB_WIRING, "Constant", attrs, "const", 40, 80)


def dff():
    """Ends: 0 = D, 1 = CLK, 2 = Q, 3 = Q', 4 = Reset, 5 = Set."""
    return Comp(LIB_MEMORY, "D Flip-Flop", {}, "dff", 80, 120)


def clock(label):
    return Comp(LIB_WIRING, "Clock", {"label": label}, "clock", 40, 80)


def led(label):
    return Comp(LIB_IO, "LED", {"label": label}, "led", 40, 80)


def seven_seg_display():
    """Ends 0..6 = segments a..g, 7 = dp."""
    return Comp(LIB_IO, "7-Segment Display", {}, "display", 100, 100)


def sub(name, n_ports):
    return Comp(None, name, {}, "sub", n_ports * 20 + 60, 420)


class Block:
    """A subcircuit with an ordered port list."""

    def __init__(self, name, inputs, outputs):
        self.name = name
        self.inputs, self.outputs = inputs, outputs  # [(label, width)]
        self.columns = []

    def column(self, comps):
        self.columns.append(list(comps))
        return comps

    # -- layout -------------------------------------------------------------
    def layout(self):
        """Pins on the sides, component columns in between, all on a 10 grid.

        Input pins share one x and step down in table order, so Logisim's
        (y, x) port ordering gives exactly the listed order. Same for outputs.
        """
        self.pins = []
        y = 100
        for label, width in self.inputs:
            self.pins.append((label, width, False, (100, y)))
            y += 60
        x = 300
        for col in self.columns:
            col_w = max(c.width_px for c in col)
            y = 100
            for c in col:
                c.loc = (x + col_w - 20, y)
                y += c.height + 20
            x += col_w + 60
        y = 100
        for label, width in self.outputs:
            self.pins.append((label, width, True, (x + 100, y)))
            y += 60

    # -- XML ----------------------------------------------------------------
    def element(self, tunnels=()):
        c = ET.Element("circuit", name=self.name)
        for k, v in (("appearance", "logisim_evolution"), ("circuit", self.name),
                     ("circuitnamedboxfixedsize", "true"), ("simulationFrequency", "1.0")):
            ET.SubElement(c, "a", name=k, val=v)
        for label, width, is_out, loc in self.pins:
            p = ET.SubElement(c, "comp", lib=LIB_WIRING, loc=fmt(loc), name="Pin")
            ET.SubElement(p, "a", name="appearance", val="classic")
            ET.SubElement(p, "a", name="label", val=label)
            if is_out:
                ET.SubElement(p, "a", name="type", val="output")
            if width != 1:
                ET.SubElement(p, "a", name="width", val=str(width))
        for col in self.columns:
            for comp in col:
                attrs = {"loc": fmt(comp.loc), "name": comp.name}
                if comp.lib is not None:
                    attrs = {"lib": comp.lib, **attrs}
                e = ET.SubElement(c, "comp", attrs)
                for k, v in comp.attrs.items():
                    ET.SubElement(e, "a", name=k, val=v)
        for net, width, loc in tunnels:
            e = ET.SubElement(c, "comp", lib=LIB_WIRING, loc=fmt(loc), name="Tunnel")
            ET.SubElement(e, "a", name="label", val=net)
            if width != 1:
                ET.SubElement(e, "a", name="width", val=str(width))
        return c

    # -- nets ---------------------------------------------------------------
    def wanted(self):
        """Yield (component loc, port key, net) for every connection."""
        for label, _w, _o, loc in self.pins:
            yield loc, "pin", label  # a pin's net is named after the pin
        for col in self.columns:
            for comp in col:
                for port, net in comp.ports.items():
                    yield comp.loc, port, net


def fmt(loc):
    return f"({loc[0]},{loc[1]})"


# -- probing ----------------------------------------------------------------

def probe(circ_path, jar):
    """Run Probe.java on a file; returns (ends, ports) per circuit."""
    cls = os.path.join(PROBE_DIR, "Probe.class")
    src = os.path.join(PROBE_DIR, "Probe.java")
    if not os.path.exists(cls) or os.path.getmtime(cls) < os.path.getmtime(src):
        subprocess.run(["javac", "-cp", jar, src], check=True)
    cmd = ["java", "-Djava.awt.headless=false", "-cp", f"{jar}{os.pathsep}{PROBE_DIR}",
           "Probe", circ_path]
    if os.environ.get("DISPLAY") is None and shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    ends = defaultdict(list)   # circuit -> [(factory, comp_loc, idx, loc, width, dir)]
    ports = defaultdict(dict)  # circuit -> {(comp_loc, pin_label): loc}
    for line in out.splitlines():
        f = line.split("\t")
        if f[0] == "END":
            ends[f[1]].append((f[2], xy(f[3]), int(f[5]), xy(f[6]), int(f[7]), f[8]))
        elif f[0] == "PORT":
            ports[f[1]][(xy(f[3]), f[4])] = xy(f[5])
    return ends, ports


def xy(s):
    a, b = s.split(",")
    return int(a), int(b)


def resolve(block, ends, ports):
    """Map every wanted connection to a real (net, width, location)."""
    by_comp = defaultdict(dict)
    for factory, cloc, idx, loc, width, _d in ends[block.name]:
        by_comp[cloc][idx] = (loc, width, factory)
    result = []
    for cloc, port, net in block.wanted():
        comp_ends = by_comp.get(cloc)
        if not comp_ends:
            raise RuntimeError(f"{block.name}: no component found at {cloc}")
        factory = next(iter(comp_ends.values()))[2]
        if port == "pin":
            idx = 0
        elif port == "out" or port == "bus":
            idx = 0
        elif port.startswith("in") and port[2:].isdigit():
            idx = int(port[2:]) + 1
        elif port.startswith("end") and port[3:].isdigit():
            idx = int(port[3:])
        elif port.startswith("b") and port[1:].isdigit() and factory == "Splitter":
            idx = int(port[1:]) + 1
        else:  # subcircuit port, by pin label as Logisim reports it
            loc = ports[block.name].get((cloc, port))
            if loc is None:
                raise RuntimeError(f"{block.name}: {factory} at {cloc} has no port {port}")
            width = next(w for l, w, _f in comp_ends.values() if l == loc)
            result.append((net, width, loc))
            continue
        if idx not in comp_ends:
            raise RuntimeError(f"{block.name}: {factory} at {cloc} has no end {idx}")
        loc, width, _f = comp_ends[idx]
        result.append((net, width, loc))
    return result


def check(block, ends):
    """Electrical sanity checks on the final probed circuit."""
    at = defaultdict(list)
    for factory, cloc, idx, loc, width, d in ends[block.name]:
        at[loc].append((factory, cloc, idx, width))
    errors = []
    for loc, items in at.items():
        tunnels = [i for i in items if i[0] == "Tunnel"]
        others = [i for i in items if i[0] != "Tunnel"]
        if len(others) > 1:
            errors.append(f"ports collide at {loc}: {others}")
        if len(tunnels) > 1:
            errors.append(f"two tunnels at {loc}")
    return errors


def build(base_path, out_path, blocks, jar):
    """Replace the scripted circuits in base_path and write out_path."""
    tree = ET.parse(base_path)
    root = tree.getroot()
    names = {b.name for b in blocks}
    for c in list(root.findall("circuit")):
        if c.get("name") in names:
            root.remove(c)
    for b in blocks:
        b.layout()

    def write(tunnel_map):
        for c in list(root.findall("circuit")):
            if c.get("name") in names:
                root.remove(c)
        for b in blocks:
            root.append(b.element(tunnel_map.get(b.name, ())))
        ET.indent(tree, space="  ")
        tree.write(out_path, encoding="UTF-8", xml_declaration=True)

    write({})
    ends, ports = probe(out_path, jar)
    tunnel_map = {}
    for b in blocks:
        conns = resolve(b, ends, ports)
        widths = defaultdict(set)
        count = defaultdict(int)
        for net, width, _loc in conns:
            widths[net].add(width)
            count[net] += 1
        bad = [f"net {n} has widths {w}" for n, w in widths.items() if len(w) > 1]
        bad += [f"net {n} has only one port" for n, k in count.items() if k < 2]
        if bad:
            raise RuntimeError(f"{b.name}: " + "; ".join(bad))
        tunnel_map[b.name] = conns
    write(tunnel_map)
    ends, _ = probe(out_path, jar)
    errors = []
    for b in blocks:
        errors += [f"{b.name}: {e}" for e in check(b, ends)]
    if errors:
        raise RuntimeError("\n".join(errors))
