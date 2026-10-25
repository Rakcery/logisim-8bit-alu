#!/usr/bin/env python3
"""Generate the repetitive v2 subcircuits into ALU.circ (in place).

Only the circuits listed in BLOCKS are replaced; hand-drawn circuits and the
reused v1 circuits are left untouched. Port orders are listed in docs/blocks.md.

Usage: python3 tools/gen_blocks.py ALU.circ path/to/logisim-evolution.jar
"""
import sys

import os

from asm import assemble, rom_contents
from circgen import (Block, build, clock, constant, dff, gate, led, rom, seven_seg_display,
                     splitter, sub)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

N = 8


def split(bus, prefix, width=N):
    """Splitter tying an N-bit bus net to nets prefix0..prefix{N-1}."""
    s = splitter(width).to("bus", bus)
    for k in range(width):
        s.to(f"b{k}", f"{prefix}{k}")
    return s


def adder8bit():
    """8x FullAdder ripple carry. V = C7 XOR C8 (carry into / out of MSB)."""
    b = Block("Adder8bit", [("A", 8), ("B", 8), ("Cin", 1)],
              [("S", 8), ("Cout", 1), ("V", 1)])
    b.column([split("A", "a"), split("B", "b")])
    fas = []
    for k in range(N):
        cin = "Cin" if k == 0 else f"c{k}"
        cout = "Cout" if k == N - 1 else f"c{k + 1}"
        fas.append(sub("FullAdder", 3).to("A", f"a{k}").to("B", f"b{k}").to("Cin", cin)
                   .to("Sum", f"s{k}").to("Cout", cout))
    b.column(fas)
    b.column([gate("XOR Gate").to("in0", "c7").to("in1", "Cout").to("out", "V"),
              split("S", "s")])
    return b


def subtractor8bit():
    """A + ~B + 1. Cout = 1 means no borrow (A >= B unsigned)."""
    b = Block("Subtractor8bit", [("A", 8), ("B", 8)], [("S", 8), ("Cout", 1), ("V", 1)])
    b.column([split("B", "b")])
    b.column([gate("NOT Gate").to("in0", f"b{k}").to("out", f"nb{k}") for k in range(N)])
    b.column([split("nB", "nb"), constant(1, 1).to("out", "one")])
    b.column([sub("Adder8bit", 3).to("A", "A").to("B", "nB").to("Cin", "one")
              .to("S", "S").to("Cout", "Cout").to("V", "V")])
    return b


def incdec(name, b_value, cin):
    b = Block(name, [("A", 8)], [("S", 8), ("Cout", 1), ("V", 1)])
    b.column([constant(8, b_value).to("out", "k"), constant(1, cin).to("out", "cin")])
    b.column([sub("Adder8bit", 3).to("A", "A").to("B", "k").to("Cin", "cin")
              .to("S", "S").to("Cout", "Cout").to("V", "V")])
    return b


def register8bit():
    """Two v1 Register4bit blocks sharing Load and CLK."""
    b = Block("Register8bit", [("Load", 1), ("D", 8), ("CLK", 1)], [("Q", 8)])
    b.column([split("D", "d")])
    regs = []
    for half in range(2):
        r = sub("Register4bit", 6).to("Load", "Load").to("CLK", "CLK")
        for k in range(4):
            r.to(f"D{k}", f"d{half * 4 + k}").to(f"Q{k}", f"q{half * 4 + k}")
        regs.append(r)
    b.column(regs)
    b.column([split("Q", "q")])
    return b


def logicunit8():
    b = Block("LogicUnit8", [("A", 8), ("B", 8)],
              [("And", 8), ("Or", 8), ("Xor", 8), ("NotA", 8)])
    b.column([split("A", "a"), split("B", "b")])
    for gname, net in (("AND Gate", "and"), ("OR Gate", "or"), ("XOR Gate", "xor")):
        b.column([gate(gname).to("in0", f"a{k}").to("in1", f"b{k}").to("out", f"{net}{k}")
                  for k in range(N)])
    b.column([gate("NOT Gate").to("in0", f"a{k}").to("out", f"not{k}") for k in range(N)])
    b.column([split("And", "and"), split("Or", "or"), split("Xor", "xor"),
              split("NotA", "not")])
    return b


def comparator8bit():
    """Two hand-drawn Comparator4bitGTEQ blocks; the low nibble feeds the high one."""
    b = Block("Comparator8bit", [("A", 8), ("B", 8)], [("GT", 1), ("EQ", 1), ("GTE", 1)])
    b.column([split("A", "a"), split("B", "b"),
              constant(1, 0).to("out", "zero"), constant(1, 1).to("out", "one")])
    cmps = []
    for half, gtin, eqin, gt, eq in ((0, "zero", "one", "gtl", "eql"), (1, "gtl", "eql", "GT", "EQ")):
        c = sub("Comparator4bitGTEQ", 10).to("GTin", gtin).to("EQin", eqin).to("GT", gt).to("EQ", eq)
        for k in range(4):
            c.to(f"A{k}", f"a{half * 4 + k}").to(f"B{k}", f"b{half * 4 + k}")
        cmps.append(c)
    b.column(cmps)
    b.column([gate("OR Gate").to("in0", "GT").to("in1", "EQ").to("out", "GTE")])
    return b


def merge(bus, nets):
    """Splitter joining 1-bit nets (bit 0 first) into a bus; None leaves a bit open."""
    s = splitter(len(nets)).to("bus", bus)
    for k, net in enumerate(nets):
        if net is not None:
            s.to(f"b{k}", net)
    return s


def zerodetect8():
    """Z = 1 when all 8 input bits are 0 (one 8-input NOR)."""
    b = Block("ZeroDetect8", [("In", 8)], [("Z", 1)])
    b.column([split("In", "i")])
    b.column([gate("NOR Gate", N).to("out", "Z").to_many("in", [f"i{k}" for k in range(N)])])
    return b


def opmux16(width):
    """Gate-level 16:1 mux: 4->16 decoder, then per output bit 16 AND2 + one OR16."""
    name = f"OpMux16x{width}"
    b = Block(name, [("Sel", 4)] + [(f"In{i}", width) for i in range(16)], [("Out", width)])
    b.column([split("Sel", "s", 4)] + [split(f"In{i}", f"in{i}_", width) for i in range(16)])
    b.column([gate("NOT Gate").to("in0", f"s{k}").to("out", f"ns{k}") for k in range(4)])
    dec = []
    for i in range(16):
        g = gate("AND Gate", 4).to("out", f"d{i}")
        for k in range(4):
            g.to(f"in{k}", f"s{k}" if (i >> k) & 1 else f"ns{k}")
        dec.append(g)
    b.column(dec)
    for k in range(width):
        b.column([gate("AND Gate").to("in0", f"d{i}").to("in1", f"in{i}_{k}").to("out", f"t{k}_{i}")
                  for i in range(16)])
    b.column([gate("OR Gate", 16).to("out", f"o{k}").to_many("in", [f"t{k}_{i}" for i in range(16)])
              for k in range(width)])
    b.column([merge("Out", [f"o{k}" for k in range(width)])])
    return b


def divstep8():
    """One restoring-division step, 8-bit version of v1 DivStepFull.

    R is the already shifted partial remainder. q = (R >= B) AND (B != 0);
    N = q ? R - B : R; Qout = {Qin[6:0], q}.
    """
    b = Block("DivStep8", [("R", 8), ("B", 8), ("Qin", 8)], [("N", 8), ("Qout", 8)])
    # Qin bit 7 is shifted out and left unconnected.
    b.column([split("B", "b"), merge("Qin", [f"qi{k}" for k in range(N - 1)] + [None])])
    b.column([gate("OR Gate", N).to("out", "bnz").to_many("in", [f"b{k}" for k in range(N)]),
              sub("Comparator8bit", 3).to("A", "R").to("B", "B").to("GTE", "gte"),
              sub("Subtractor8bit", 3).to("A", "R").to("B", "B").to("S", "diff")])
    b.column([gate("AND Gate").to("in0", "gte").to("in1", "bnz").to("out", "q")])
    b.column([sub("Select8bit", 3).to("Sel", "q").to("X", "R").to("Y", "diff").to("Out", "N"),
              merge("Qout", ["q"] + [f"qi{k}" for k in range(N - 1)])])
    return b


def div8bit():
    """8 chained DivStep8 (MSB of A first). B = 0 gives Q = 0, R = A, DZ = 1."""
    b = Block("DIV8bit", [("A", 8), ("B", 8)], [("Q", 8), ("R", 8), ("DZ", 1)])
    b.column([split("A", "a"), constant(1, 0).to("out", "zero"), constant(8, 0).to("out", "q_init"),
              sub("ZeroDetect8", 1).to("In", "B").to("Z", "DZ")])
    shifts, steps = [], []
    for s in range(N):
        high = ["zero"] * (N - 1) if s == 0 else [f"n{s - 1}_{j}" for j in range(N - 1)]
        shifts.append(merge(f"rin{s}", [f"a{N - 1 - s}"] + high))
        last = s == N - 1
        steps.append(sub("DivStep8", 3).to("R", f"rin{s}").to("B", "B")
                     .to("Qin", "q_init" if s == 0 else f"q{s - 1}")
                     .to("N", "R" if last else f"n{s}").to("Qout", "Q" if last else f"q{s}"))
    b.column(shifts)
    b.column(steps)
    b.column([merge(f"n{s}", [f"n{s}_{j}" for j in range(N - 1)] + [None]) for s in range(N - 1)])
    return b


def mul8bit():
    """Array multiplier: 64 AND partial products summed by 7 Adder8bit rows."""
    b = Block("MUL8bit", [("A", 8), ("B", 8)], [("Lo", 8), ("Hi", 8), ("Ovf", 1)])
    b.column([split("A", "a"), split("B", "b"), constant(1, 0).to("out", "zero")])
    for j in range(N):
        out = (lambda k: f"s0_{k}") if j == 0 else (lambda k, j=j: f"pp{j}_{k}")
        b.column([gate("AND Gate").to("in0", f"a{k}").to("in1", f"b{j}").to("out", out(k))
                  for k in range(N)])
    merges, adders, splits = [], [], []
    for j in range(1, N):
        merges.append(merge(f"pp{j}", [f"pp{j}_{k}" for k in range(N)]))
        carry = "zero" if j == 1 else f"c{j - 1}"
        merges.append(merge(f"x{j}", [f"s{j - 1}_{k}" for k in range(1, N)] + [carry]))
        adders.append(sub("Adder8bit", 3).to("A", f"x{j}").to("B", f"pp{j}").to("Cin", "zero")
                      .to("S", f"sum{j}").to("Cout", f"c{j}"))
        splits.append(split(f"sum{j}", f"s{j}_"))
    b.column(merges)
    b.column(adders)
    b.column(splits)
    hi = [f"s{N - 1}_{k}" for k in range(1, N)] + [f"c{N - 1}"]
    b.column([merge("Lo", [f"s{j}_0" for j in range(N)]), merge("Hi", hi),
              gate("OR Gate", N).to("out", "Ovf").to_many("in", hi)])
    return b


def mux8_tree(prefix, inputs, out):
    """8:1 select tree of v1 Select1bit, controlled by nets amt0..amt2."""
    comps, level = [], list(inputs)
    for s in range(3):
        nxt = []
        for i in range(0, len(level), 2):
            net = out if len(level) == 2 else f"{prefix}{s}_{i // 2}"
            comps.append(sub("Select1bit", 3).to("Sel", f"amt{s}").to("X", level[i])
                         .to("Y", level[i + 1]).to("SelOut", net))
            nxt.append(net)
        level = nxt
    return comps


def barrel(name, extra_inputs, outputs, source, cout_inputs=None, fill=None):
    """3-stage barrel of Select1bit. source(stage_bits, k, dist) -> net for shifted bit."""
    b = Block(name, [("A", 8), ("Amt", 3)] + extra_inputs, outputs)
    first = [split("A", "a"), split("Amt", "amt", 3)]
    if cout_inputs:
        first.append(constant(1, 0).to("out", "zero"))
    if fill:
        first.append(gate("AND Gate").to("in0", "a7").to("in1", "Arith").to("out", "fill"))
    b.column(first)
    prev = [f"a{k}" for k in range(N)]
    for s in range(3):
        cur = [f"y{k}" if s == 2 else f"st{s}_{k}" for k in range(N)]
        b.column([sub("Select1bit", 3).to("Sel", f"amt{s}").to("X", prev[k])
                  .to("Y", source(prev, k, 1 << s)).to("SelOut", cur[k]) for k in range(N)])
        prev = cur
    last = [merge("Y", prev)]
    if cout_inputs:
        b.column(mux8_tree("cm", cout_inputs, "Cout"))
    b.column(last)
    return b


def shiftleft8():
    return barrel("ShiftLeft8", [], [("Y", 8), ("Cout", 1)],
                  lambda p, k, d: p[k - d] if k >= d else "zero",
                  cout_inputs=["zero"] + [f"a{8 - n}" for n in range(1, 8)])


def shiftright8():
    """Arith = 0: logical (SHR), Arith = 1: arithmetic (SAR)."""
    return barrel("ShiftRight8", [("Arith", 1)], [("Y", 8), ("Cout", 1)],
                  lambda p, k, d: p[k + d] if k + d < N else "fill",
                  cout_inputs=["zero"] + [f"a{n - 1}" for n in range(1, 8)], fill=True)


def rotateleft8():
    return barrel("RotateLeft8", [], [("Y", 8)], lambda p, k, d: p[(k - d) % N])


def rotateright8():
    return barrel("RotateRight8", [], [("Y", 8)], lambda p, k, d: p[(k + d) % N])


def select8bit():
    """8x v1 Select1bit. Sel=0 -> X, Sel=1 -> Y."""
    b = Block("Select8bit", [("Sel", 1), ("X", 8), ("Y", 8)], [("Out", 8)])
    b.column([split("X", "x"), split("Y", "y")])
    b.column([sub("Select1bit", 3).to("Sel", "Sel").to("X", f"x{k}").to("Y", f"y{k}")
              .to("SelOut", f"o{k}") for k in range(N)])
    b.column([split("Out", "o")])
    return b


# Dependency order: a block must come after the blocks it instantiates.
def alucore8():
    """Top-level datapath: every operation block feeds OpMux16x8 (R) and OpMux16x2 (C, V)."""
    b = Block("ALUCore8", [("A", 8), ("B", 8), ("Op", 4)], [("R", 8), ("Z", 1), ("C", 1), ("S", 1), ("V", 1)])
    b.column([merge("B", ["b0", "b1", "b2"] + [None] * 5), merge("Amt", ["b0", "b1", "b2"]), constant(1, 0).to("out", "zero"),
              constant(1, 1).to("out", "one"), constant(2, 0).to("out", "cvzero")])
    b.column([
        sub("Adder8bit", 3).to("A", "A").to("B", "B").to("Cin", "zero").to("S", "r0").to("Cout", "c0").to("V", "v0"),
        sub("Subtractor8bit", 3).to("A", "A").to("B", "B").to("S", "r1").to("Cout", "c1").to("V", "v1"),
        sub("INC8bit", 3).to("A", "A").to("S", "r2").to("Cout", "c2").to("V", "v2"),
        sub("DEC8bit", 3).to("A", "A").to("S", "r3").to("Cout", "c3").to("V", "v3"),
        sub("LogicUnit8", 4).to("A", "A").to("B", "B").to("And", "r5").to("Or", "r6").to("Xor", "r7").to("NotA", "r8"),
        sub("DIV8bit", 3).to("A", "A").to("B", "B").to("Q", "r4").to("R", "r9").to("DZ", "dz"),
        sub("MUL8bit", 3).to("A", "A").to("B", "B").to("Lo", "r10").to("Ovf", "ovf"),
        sub("ShiftLeft8", 2).to("A", "A").to("Amt", "Amt").to("Y", "r11").to("Cout", "c11"),
        sub("ShiftRight8", 3).to("A", "A").to("Amt", "Amt").to("Arith", "zero").to("Y", "r12").to("Cout", "c12"),
        sub("ShiftRight8", 3).to("A", "A").to("Amt", "Amt").to("Arith", "one").to("Y", "r13").to("Cout", "c13"),
        sub("RotateLeft8", 2).to("A", "A").to("Amt", "Amt").to("Y", "r14"),
        sub("RotateRight8", 2).to("A", "A").to("Amt", "Amt").to("Y", "r15")])
    cv = {0: ("c0", "v0"), 1: ("c1", "v1"), 2: ("c2", "v2"), 3: ("c3", "v3"), 4: ("zero", "dz"),
          9: ("zero", "dz"), 10: ("ovf", "ovf"), 11: ("c11", "zero"), 12: ("c12", "zero"), 13: ("c13", "zero")}
    b.column([merge(f"cv{i}", list(cv[i])) for i in cv])
    m8 = sub("OpMux16x8", 17).to("Sel", "Op").to("Out", "R")
    m2 = sub("OpMux16x2", 17).to("Sel", "Op").to("Out", "cvout")
    for i in range(16):
        m8.to(f"In{i}", f"r{i}")
        m2.to(f"In{i}", f"cv{i}" if i in cv else "cvzero")
    b.column([m8, m2])
    b.column([sub("ZeroDetect8", 1).to("In", "R").to("Z", "Z"), split("R", "rr"),
              merge("cvout", ["C", "V"])])
    b.columns[-1][1].ports = {"bus": "R", "b7": "S"}
    return b


# Hex 7-segment patterns, segments a..g, for digits 0..F.
HEX_SEGMENTS = ["1111110", "0110000", "1101101", "1111001", "0110011", "1011011", "1011111",
                "1110000", "1111111", "1111011", "1110111", "0011111", "1001110", "0111101",
                "1001111", "1000111"]


def hexdecoder7():
    """4-bit value -> segments a..g for 0-9, A, b, C, d, E, F (4->16 decoder + one OR per segment).

    Replaces v1 SevenSegment in main, which lights the wrong segments for 6, 7, d and E.
    """
    b = Block("HexDecoder7", [("In", 4)], [(seg, 1) for seg in "abcdefg"])
    b.column([split("In", "i", 4)])
    b.column([gate("NOT Gate").to("in0", f"i{k}").to("out", f"ni{k}") for k in range(4)])
    dec = []
    for v in range(16):
        g = gate("AND Gate", 4).to("out", f"d{v}")
        for k in range(4):
            g.to(f"in{k}", f"i{k}" if (v >> k) & 1 else f"ni{k}")
        dec.append(g)
    b.column(dec)
    b.column([gate("OR Gate", sum(p[n] == "1" for p in HEX_SEGMENTS)).to("out", seg)
              .to_many("in", [f"d{v}" for v, p in enumerate(HEX_SEGMENTS) if p[n] == "1"])
              for n, seg in enumerate("abcdefg")])
    return b


def add3():
    """Double-dabble cell: Out = In + 3 when In >= 5, else In."""
    b = Block("Add3", [("In", 4)], [("Out", 4)])
    b.column([split("In", "x", 4)])
    b.column([gate("OR Gate").to_many("in", ["x1", "x0"]).to("out", "x10")])
    b.column([gate("AND Gate").to_many("in", ["x2", "x10"]).to("out", "x210")])
    b.column([gate("OR Gate").to_many("in", ["x3", "x210"]).to("out", "ge5")])
    b.column([sub("HalfAdder", 2).to("A", "x0").to("B", "ge5").to("Sum", "y0").to("Carry", "c1"),
              sub("FullAdder", 3).to("A", "x1").to("B", "ge5").to("Cin", "c1").to("Sum", "y1").to("Cout", "c2"),
              sub("HalfAdder", 2).to("A", "x2").to("B", "c2").to("Sum", "y2").to("Carry", "c3"),
              gate("XOR Gate").to_many("in", ["x3", "c3"]).to("out", "y3")])
    b.column([merge("Out", [f"y{k}" for k in range(4)])])
    return b


def bintobcd8():
    """8-bit binary to three decimal digits with 7 Add3 cells (shift-and-add-3)."""
    b = Block("BinToBCD8", [("In", 8)], [("Hundreds", 4), ("Tens", 4), ("Ones", 4)])
    b.column([split("In", "i"), constant(1, 0).to("out", "zero")])
    # Each cell takes 4 bits, most significant first; o<n>_<k> is bit k of cell n's output.
    cells = {1: ["zero", "i7", "i6", "i5"], 2: ["o1_2", "o1_1", "o1_0", "i4"],
             3: ["o2_2", "o2_1", "o2_0", "i3"], 4: ["o3_2", "o3_1", "o3_0", "i2"],
             5: ["o4_2", "o4_1", "o4_0", "i1"], 6: ["zero", "o1_3", "o2_3", "o3_3"],
             7: ["o6_2", "o6_1", "o6_0", "o4_3"]}
    b.column([merge(f"in{n}", bits[::-1]) for n, bits in cells.items()])
    b.column([sub("Add3", 2).to("In", f"in{n}").to("Out", f"out{n}") for n in cells])
    b.column([split(f"out{n}", f"o{n}_", 4) for n in cells])
    b.column([merge("Ones", ["i0", "o5_0", "o5_1", "o5_2"]),
              merge("Tens", ["o5_3", "o7_0", "o7_1", "o7_2"]),
              merge("Hundreds", ["o7_3", "o6_3", "zero", "zero"])])
    return b


def controlunit():
    """Moore FSM, state S1S0: IDLE 00 -Load-> LOAD 01 -> EXECUTE 10 -Execute-> DISPLAY 11 -> IDLE.

    Reset is synchronous. LoadAB is high in LOAD, so RegA/RegB latch on the edge
    that leaves LOAD; LoadOut is high in EXECUTE, so the result and flags are
    latched on the edge into DISPLAY.
    """
    b = Block("ControlUnit", [("CLK", 1), ("Reset", 1), ("Load", 1), ("Execute", 1)],
              [("LoadAB", 1), ("LoadOut", 1), ("S0", 1), ("S1", 1)])
    b.column([gate("NOT Gate").to("in0", "Reset").to("out", "nreset"),
              gate("AND Gate", 3).to_many("in", ["ns1", "ns0", "Load"]).to("out", "go_load"),
              gate("AND Gate", 3).to_many("in", ["S1", "ns0", "Execute"]).to("out", "go_disp"),
              gate("XOR Gate").to_many("in", ["S1", "S0"]).to("out", "adv1")])
    b.column([gate("OR Gate").to_many("in", ["go_load", "go_disp"]).to("out", "adv0"),
              gate("AND Gate").to_many("in", ["adv0", "nreset"]).to("out", "d0"),
              gate("AND Gate").to_many("in", ["adv1", "nreset"]).to("out", "d1")])
    b.column([dff().to("end0", "d0").to("end1", "CLK").to("end2", "S0").to("end3", "ns0"),
              dff().to("end0", "d1").to("end1", "CLK").to("end2", "S1").to("end3", "ns1")])
    b.column([gate("AND Gate").to_many("in", ["ns1", "S0"]).to("out", "LoadAB"),
              gate("AND Gate").to_many("in", ["S1", "ns0"]).to("out", "LoadOut")])
    return b


def labeled(comp, label):
    comp.attrs["label"] = label
    return comp


def decimal_digits():
    """Three HexDecoder7 + displays for nets dh, dt, do; hundreds and tens go dark when hon / ton are 0."""
    decoders, blanks, displays = [], [], []
    for digit, on in (("dh", "hon"), ("dt", "ton"), ("do", None)):
        dec = sub("HexDecoder7", 7).to("In", digit)
        disp = seven_seg_display()
        for k, seg in enumerate("abcdefg"):
            dec.to(seg, f"{digit}_{seg}" if on else f"{digit}_{seg}_on")
            disp.to(f"end{k}", f"{digit}_{seg}_on")
            if on:
                blanks.append(gate("AND Gate").to_many("in", [f"{digit}_{seg}", on]).to("out", f"{digit}_{seg}_on"))
        decoders.append(dec)
        displays.append(disp)
    return decoders, blanks, displays


def main_circuit():
    """Top level: registers, ALUCore8, ControlUnit, two hex digits, three decimal digits and flag LEDs.

    The R, Z, C, S, V, S0, S1 and Dec output pins mirror the displays so the circuit
    can be checked by test vectors. Leading zeros of the decimal display stay dark.
    """
    b = Block("main", [("A", 8), ("B", 8), ("Op", 4), ("Load", 1), ("Execute", 1), ("Reset", 1)],
              [("R", 8), ("Z", 1), ("C", 1), ("S", 1), ("V", 1), ("S0", 1), ("S1", 1), ("Dec", 12)])
    b.column([clock("CLK").to("end0", "clk")])
    b.column([sub("ControlUnit", 4).to("CLK", "clk").to("Reset", "Reset").to("Load", "Load")
              .to("Execute", "Execute").to("LoadAB", "lab").to("LoadOut", "lout")
              .to("S0", "S0").to("S1", "S1"),
              labeled(sub("Register8bit", 3), "RegisterA").to("Load", "lab").to("D", "A")
              .to("CLK", "clk").to("Q", "qa"),
              labeled(sub("Register8bit", 3), "RegisterB").to("Load", "lab").to("D", "B")
              .to("CLK", "clk").to("Q", "qb")])
    b.column([sub("ALUCore8", 5).to("A", "qa").to("B", "qb").to("Op", "Op").to("R", "r")
              .to("Z", "z").to("C", "c").to("S", "s").to("V", "v")])
    flags = labeled(sub("Register4bit", 6), "FlagRegister").to("Load", "lout").to("CLK", "clk")
    for k, (d, q) in enumerate([("z", "Z"), ("c", "C"), ("s", "S"), ("v", "V")]):
        flags.to(f"D{k}", d).to(f"Q{k}", q)
    b.column([labeled(sub("Register8bit", 3), "OutputRegister").to("Load", "lout").to("D", "r")
              .to("CLK", "clk").to("Q", "R"), flags, split("R", "rq"),
              sub("BinToBCD8", 3).to("In", "R").to("Hundreds", "dh").to("Tens", "dt").to("Ones", "do")])
    b.column([merge("rq_lo", [f"rq{k}" for k in range(4)]),
              merge("rq_hi", [f"rq{k}" for k in range(4, 8)]),
              split("dh", "dh", 4), split("dt", "dt", 4), split("do", "do", 4)])
    b.column([merge("Dec", [f"do{k}" for k in range(4)] + [f"dt{k}" for k in range(4)]
                    + [f"dh{k}" for k in range(4)]),
              gate("OR Gate", 4).to_many("in", [f"dh{k}" for k in range(4)]).to("out", "hon"),
              gate("OR Gate", 5).to_many("in", ["hon"] + [f"dt{k}" for k in range(4)]).to("out", "ton")])
    decoders, displays = [], []
    for digit, low in (("hi", 4), ("lo", 0)):
        dec = sub("HexDecoder7", 7).to("In", f"rq_{digit}")
        disp = seven_seg_display()
        for k, seg in enumerate("abcdefg"):
            dec.to(seg, f"{digit}_{seg}")
            disp.to(f"end{k}", f"{digit}_{seg}")
        decoders.append(dec)
        displays.append(disp)
    dec_d, blanks, disp_d = decimal_digits()
    decoders += dec_d
    displays += disp_d
    b.column(decoders)
    b.column(blanks)
    b.column(displays + [led(f"{f}Led").to("end0", f) for f in "ZCSV"]
             + [led(f"State{k}Led").to("end0", f"S{k}") for k in range(2)])
    return b


def mux4x8(sel, inputs, out, tag):
    """4:1 selector for 8-bit buses from three Select8bit; sel is a 2-bit net."""
    return [split(sel, f"{tag}s", 2),
            sub("Select8bit", 3).to("Sel", f"{tag}s0").to("X", inputs[0]).to("Y", inputs[1]).to("Out", f"{tag}01"),
            sub("Select8bit", 3).to("Sel", f"{tag}s0").to("X", inputs[2]).to("Y", inputs[3]).to("Out", f"{tag}23"),
            sub("Select8bit", 3).to("Sel", f"{tag}s1").to("X", f"{tag}01").to("Y", f"{tag}23").to("Out", out)]


def regfile4x8():
    """Four Register8bit, one write port, two read ports. Reset clears all four on the clock edge.

    R0..R3 are extra outputs so the registers can be watched and tested.
    """
    b = Block("RegFile4x8", [("D", 8), ("WSel", 2), ("WE", 1), ("RSelA", 2), ("RSelB", 2), ("CLK", 1),
                             ("Reset", 1)],
              [("QA", 8), ("QB", 8), ("R0", 8), ("R1", 8), ("R2", 8), ("R3", 8)])
    b.column([split("WSel", "w", 2), constant(8, 0).to("out", "zero8")])
    b.column([gate("NOT Gate").to("in0", f"w{k}").to("out", f"nw{k}") for k in range(2)]
             + [sub("Select8bit", 3).to("Sel", "Reset").to("X", "D").to("Y", "zero8").to("Out", "dd")])
    b.column([gate("AND Gate", 3).to_many("in", ["WE", "w1" if i >> 1 else "nw1", "w0" if i & 1 else "nw0"])
              .to("out", f"we{i}") for i in range(4)])
    b.column([gate("OR Gate").to_many("in", [f"we{i}", "Reset"]).to("out", f"ld{i}") for i in range(4)])
    b.column([labeled(sub("Register8bit", 3), f"R{i}").to("Load", f"ld{i}").to("D", "dd").to("CLK", "CLK")
              .to("Q", f"R{i}") for i in range(4)])
    regs = [f"R{i}" for i in range(4)]
    b.column(mux4x8("RSelA", regs, "QA", "a") + mux4x8("RSelB", regs, "QB", "b"))
    return b


def pc8():
    """Program counter: Q+1 every tick, D when Jump, unchanged when Hold, 0 after Reset."""
    b = Block("PC8", [("D", 8), ("Jump", 1), ("Hold", 1), ("CLK", 1), ("Reset", 1)], [("Q", 8)])
    b.column([sub("INC8bit", 3).to("A", "Q").to("S", "inc"), constant(8, 0).to("out", "zero8"),
              gate("NOT Gate").to("in0", "Hold").to("out", "nhold")])
    b.column([sub("Select8bit", 3).to("Sel", "Jump").to("X", "inc").to("Y", "D").to("Out", "nx"),
              gate("OR Gate").to_many("in", ["nhold", "Reset"]).to("out", "ld")])
    b.column([sub("Select8bit", 3).to("Sel", "Reset").to("X", "nx").to("Y", "zero8").to("Out", "dd")])
    b.column([sub("Register8bit", 3).to("Load", "ld").to("D", "dd").to("CLK", "CLK").to("Q", "Q")])
    return b


def decoder16():
    """Instruction word -> control signals. op = Instr[15:12]; ALU opcode = Instr[3:0].

    0000 ALU, 0001 LDI, 0010 MOV, 0011 JMP, 0100 JZ, 0101 JNZ, 0110 JC, 0111 OUT, 1000 HALT.
    WSrc: 00 = ALU result, 01 = immediate (LDI), 10 = rs (MOV). 1001-1111 do nothing.
    """
    b = Block("Decoder16", [("Instr", 16), ("Z", 1), ("C", 1)],
              [("AluOp", 4), ("RegWrite", 1), ("WSrc", 2), ("Jump", 1), ("FlagWrite", 1),
               ("OutWrite", 1), ("Halt", 1)])
    # rd, rs and imm[7:4] are not needed here.
    b.column([merge("Instr", [f"i{k}" for k in range(4)] + [None] * 8 + [f"i{k}" for k in range(12, 16)])])
    b.column([gate("NOT Gate").to("in0", f"i{k}").to("out", f"ni{k}") for k in range(12, 16)]
             + [gate("NOT Gate").to("in0", "Z").to("out", "nz"), merge("AluOp", [f"i{k}" for k in range(4)])])
    names = {0: "FlagWrite", 1: "ldi", 2: "mov", 3: "jmp", 4: "jz", 5: "jnz", 6: "jc", 7: "OutWrite", 8: "Halt"}
    b.column([gate("AND Gate", 4).to_many("in", [f"i{k}" if (op >> (k - 12)) & 1 else f"ni{k}" for k in range(12, 16)])
              .to("out", net) for op, net in names.items()])
    b.column([gate("AND Gate").to_many("in", ["jz", "Z"]).to("out", "tz"),
              gate("AND Gate").to_many("in", ["jnz", "nz"]).to("out", "tnz"),
              gate("AND Gate").to_many("in", ["jc", "C"]).to("out", "tc"),
              gate("OR Gate", 3).to_many("in", ["FlagWrite", "ldi", "mov"]).to("out", "RegWrite"),
              merge("WSrc", ["ldi", "mov"])])
    b.column([gate("OR Gate", 4).to_many("in", ["jmp", "tz", "tnz", "tc"]).to("out", "Jump")])
    return b


def cpu_circuit():
    """Single-cycle mini CPU: ROM -> Decoder16 -> RegFile4x8 + ALUCore8, one instruction per tick.

    The ROM holds programs/fibonacci.asm. Reset (synchronous) sets PC, registers, flags and the
    display to 0. Output pins mirror the state so programs can be checked by test vectors.
    """
    words = assemble(open(os.path.join(ROOT, "programs", "fibonacci.asm")).read())
    b = Block("cpu", [("Reset", 1)],
              [("PC", 8), ("R0", 8), ("R1", 8), ("R2", 8), ("R3", 8), ("Out", 8), ("Z", 1), ("C", 1), ("Halt", 1)])
    b.column([clock("CLK").to("end0", "clk"), constant(8, 0).to("out", "zero8"),
              constant(1, 0).to("out", "zero"), gate("NOT Gate").to("in0", "Reset").to("out", "nreset")])
    b.column([labeled(sub("PC8", 5), "PC").to("D", "imm").to("Jump", "Jump").to("Hold", "Halt").to("CLK", "clk")
              .to("Reset", "Reset").to("Q", "PC")])
    b.column([labeled(rom(rom_contents(words)), "Program").to("end0", "PC").to("end1", "instr")])
    b.column([merge("instr", [f"in{k}" for k in range(12)] + [None] * 4),
              sub("Decoder16", 7).to("Instr", "instr").to("Z", "Z").to("C", "C").to("AluOp", "aluop")
              .to("RegWrite", "RegWrite").to("WSrc", "wsrc").to("Jump", "Jump").to("FlagWrite", "FlagWrite")
              .to("OutWrite", "OutWrite").to("Halt", "Halt")])
    b.column([merge("rd", ["in10", "in11"]), merge("rs", ["in8", "in9"]), merge("imm", [f"in{k}" for k in range(8)]),
              split("wsrc", "ws", 2)])
    b.column([sub("RegFile4x8", 7).to("D", "wd").to("WSel", "rd").to("WE", "RegWrite").to("RSelA", "rd")
              .to("RSelB", "rs").to("CLK", "clk").to("Reset", "Reset").to("QA", "qa").to("QB", "qb")
              .to("R0", "R0").to("R1", "R1").to("R2", "R2").to("R3", "R3")])
    b.column([sub("ALUCore8", 5).to("A", "qa").to("B", "qb").to("Op", "aluop").to("R", "r").to("Z", "az")
              .to("C", "ac")])
    b.column([sub("Select8bit", 3).to("Sel", "ws0").to("X", "r").to("Y", "imm").to("Out", "w1"),
              gate("AND Gate").to_many("in", ["az", "nreset"]).to("out", "fz"),
              gate("AND Gate").to_many("in", ["ac", "nreset"]).to("out", "fc"),
              gate("OR Gate").to_many("in", ["FlagWrite", "Reset"]).to("out", "fld"),
              gate("OR Gate").to_many("in", ["OutWrite", "Reset"]).to("out", "old"),
              sub("Select8bit", 3).to("Sel", "Reset").to("X", "qb").to("Y", "zero8").to("Out", "od")])
    b.column([sub("Select8bit", 3).to("Sel", "ws1").to("X", "w1").to("Y", "qb").to("Out", "wd"),
              labeled(sub("Register4bit", 6), "Flags").to("Load", "fld").to("CLK", "clk")
              .to("D0", "fz").to("D1", "fc").to("D2", "zero").to("D3", "zero").to("Q0", "Z").to("Q1", "C"),
              labeled(sub("Register8bit", 3), "Display").to("Load", "old").to("D", "od").to("CLK", "clk")
              .to("Q", "Out")])
    b.column([sub("BinToBCD8", 3).to("In", "Out").to("Hundreds", "dh").to("Tens", "dt").to("Ones", "do")])
    b.column([split("dh", "dh", 4), split("dt", "dt", 4)])
    b.column([gate("OR Gate", 4).to_many("in", [f"dh{k}" for k in range(4)]).to("out", "hon"),
              gate("OR Gate", 5).to_many("in", ["hon"] + [f"dt{k}" for k in range(4)]).to("out", "ton")])
    decoders, blanks, displays = decimal_digits()
    b.column(decoders)
    b.column(blanks)
    b.column(displays + [led("HaltLed").to("end0", "Halt"), led("ZLed").to("end0", "Z"), led("CLed").to("end0", "C")])
    return b


BLOCKS = [adder8bit, subtractor8bit, lambda: incdec("INC8bit", 0x00, 1),
          lambda: incdec("DEC8bit", 0xFF, 0), register8bit, logicunit8, select8bit,
          comparator8bit, zerodetect8, lambda: opmux16(8), lambda: opmux16(2), divstep8,
          div8bit, mul8bit, shiftleft8, shiftright8, rotateleft8, rotateright8, alucore8,
          hexdecoder7, add3, bintobcd8, controlunit, main_circuit, regfile4x8, pc8, decoder16,
          cpu_circuit]


def main(circ, jar):
    build(circ, circ, [f() for f in BLOCKS], jar)
    print("built:", ", ".join(f().name for f in BLOCKS))


if __name__ == "__main__":
    main(*sys.argv[1:3])
