#!/usr/bin/env python3
"""Write Logisim test vectors for every block into tests/vectors/.

Expected values come from plain Python reference models below, never from the
circuit. Two-operand 8-bit blocks get all edge cases plus a fixed-seed random
sample; one-operand blocks are exhaustive.

Usage: python3 tests/gen_vectors.py
"""
import itertools
import os
import random
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGES = [0x00, 0x01, 0x02, 0x0F, 0x10, 0x55, 0x7E, 0x7F, 0x80, 0x81, 0xAA, 0xF0, 0xFE, 0xFF]
RANDOM_PAIRS = 2000
# ALUCore8 runs slowly in Logisim (every row re-simulates DIV and MUL), so it
# gets these hand-picked edge cases plus a thinned sample of pairs().
ALU_PAIRS = [(0x00, 0x00), (0xFF, 0x01), (0x7F, 0x01), (0x80, 0x01), (0x80, 0xFF), (0x7F, 0xFF),
             (0x05, 0x00), (0xFF, 0xFF), (0x10, 0x10), (0x81, 0x07), (0xC8, 0x03), (0x01, 0x80)]


def b(value, width):
    return format(value & ((1 << width) - 1), f"0{width}b")


def pairs():
    rng = random.Random(2026)
    seen = list(itertools.product(EDGES, EDGES))
    seen += [(rng.randrange(256), rng.randrange(256)) for _ in range(RANDOM_PAIRS)]
    return seen


def add8(a, bb, cin):
    """Returns (S, Cout, V) with V = carry into bit 7 XOR carry out of bit 7."""
    total = a + bb + cin
    c7 = ((a & 0x7F) + (bb & 0x7F) + cin) >> 7
    c8 = total >> 8
    return total & 0xFF, c8, c7 ^ c8


def alu(op, x, y):
    """Reference model of ALUCore8 (opcode table in README.md). Returns (R, Z, C, S, V)."""
    amt = y & 7
    c = v = 0
    if op <= 3:
        bb, cin = ((y, 0), (~y & 0xFF, 1), (0, 1), (0xFF, 0))[op]
        r, c, v = add8(x, bb, cin)
    elif op in (4, 9):
        r = (x // y if op == 4 else x % y) if y else (0 if op == 4 else x)
        v = int(y == 0)
    elif op in (5, 6, 7, 8):
        r = (x & y, x | y, x ^ y, ~x)[op - 5] & 0xFF
    elif op == 10:
        r, c = x * y & 0xFF, int(x * y > 255)
        v = c
    elif op == 11:
        r, c = (x << amt) & 0xFF, (x >> (8 - amt)) & 1 if amt else 0
    elif op in (12, 13):
        signed = x - 256 if (op == 13 and x & 0x80) else x
        r, c = (signed >> amt) & 0xFF, (x >> (amt - 1)) & 1 if amt else 0
    else:
        r = ((x << amt) | (x >> (8 - amt)) if op == 14 else (x >> amt) | (x << (8 - amt))) & 0xFF
    return r, int(r == 0), c, r >> 7, v


def write(name, header, rows, sequential=False):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{name}.txt"), "w") as f:
        f.write("# " + name + " (from tests/gen_vectors.py)\n")
        if sequential:
            f.write("# sequential: rows run in order on one simulation state\n")
        f.write(" ".join(header) + "\n")
        for r in rows:
            f.write(" ".join(r) + "\n")


def main():
    write("Adder8bit", ["A[8]", "B[8]", "Cin", "S[8]", "Cout", "V"],
          [[b(x, 8), b(y, 8), str(c), b(s, 8), str(co), str(v)]
           for x, y in pairs() for c in (0, 1) for s, co, v in [add8(x, y, c)]])
    write("Subtractor8bit", ["A[8]", "B[8]", "S[8]", "Cout", "V"],
          [[b(x, 8), b(y, 8), b(s, 8), str(co), str(v)]
           for x, y in pairs() for s, co, v in [add8(x, ~y & 0xFF, 1)]])
    write("INC8bit", ["A[8]", "S[8]", "Cout", "V"],
          [[b(x, 8), b(s, 8), str(co), str(v)] for x in range(256)
           for s, co, v in [add8(x, 0, 1)]])
    write("DEC8bit", ["A[8]", "S[8]", "Cout", "V"],
          [[b(x, 8), b(s, 8), str(co), str(v)] for x in range(256)
           for s, co, v in [add8(x, 0xFF, 0)]])
    write("LogicUnit8", ["A[8]", "B[8]", "And[8]", "Or[8]", "Xor[8]", "NotA[8]"],
          [[b(x, 8), b(y, 8), b(x & y, 8), b(x | y, 8), b(x ^ y, 8), b(~x, 8)]
           for x, y in pairs()])
    write("Select8bit", ["Sel", "X[8]", "Y[8]", "Out[8]"],
          [[str(s), b(x, 8), b(y, 8), b(y if s else x, 8)]
           for x, y in pairs() for s in (0, 1)])
    rows = []
    for x, y, gtin, eqin in itertools.product(range(16), range(16), (0, 1), (0, 1)):
        gt = int(x > y or (x == y and gtin))
        eq = int(x == y and eqin)
        rows.append(list(b(x, 4)) + list(b(y, 4)) + [str(gtin), str(eqin), str(gt), str(eq)])
    write("Comparator4bitGTEQ", ["A3", "A2", "A1", "A0", "B3", "B2", "B1", "B0", "GTin", "EQin",
                                 "GT", "EQ"], rows)
    write("Comparator8bit", ["A[8]", "B[8]", "GT", "EQ", "GTE"],
          [[b(x, 8), b(y, 8), str(int(x > y)), str(int(x == y)), str(int(x >= y))]
           for x, y in pairs()])
    write("ZeroDetect8", ["In[8]", "Z"], [[b(x, 8), str(int(x == 0))] for x in range(256)])
    rng = random.Random(16)
    for width in (8, 2):
        rows = []
        for _ in range(40):
            ins = [rng.randrange(1 << width) for _ in range(16)]
            for sel in range(16):
                rows.append([b(sel, 4)] + [b(v, width) for v in ins] + [b(ins[sel], width)])
        write(f"OpMux16x{width}", ["Sel[4]"] + [f"In{i}[{width}]" for i in range(16)]
              + [f"Out[{width}]"], rows)
    rows = []
    for r, d in pairs():
        qin = rng.randrange(256)
        q = int(r >= d and d != 0)
        rows.append([b(r, 8), b(d, 8), b(qin, 8), b(r - d if q else r, 8), b((qin << 1) | q, 8)])
    write("DivStep8", ["R[8]", "B[8]", "Qin[8]", "N[8]", "Qout[8]"], rows)
    write("DIV8bit", ["A[8]", "B[8]", "Q[8]", "R[8]", "DZ"],
          [[b(x, 8), b(y, 8), b(x // y if y else 0, 8), b(x % y if y else x, 8), str(int(y == 0))]
           for x, y in pairs()])
    write("MUL8bit", ["A[8]", "B[8]", "Lo[8]", "Hi[8]", "Ovf"],
          [[b(x, 8), b(y, 8), b(x * y, 8), b(x * y >> 8, 8), str(int(x * y > 255))]
           for x, y in pairs()])
    shifts = list(itertools.product(range(256), range(8)))
    write("ShiftLeft8", ["A[8]", "Amt[3]", "Y[8]", "Cout"],
          [[b(x, 8), b(n, 3), b(x << n, 8), str((x >> (8 - n)) & 1 if n else 0)] for x, n in shifts])
    rows = []
    for x, n in shifts:
        for arith in (0, 1):
            signed = x - 256 if (arith and x & 0x80) else x
            rows.append([b(x, 8), b(n, 3), str(arith), b(signed >> n, 8),
                         str((x >> (n - 1)) & 1 if n else 0)])
    write("ShiftRight8", ["A[8]", "Amt[3]", "Arith", "Y[8]", "Cout"], rows)
    write("RotateLeft8", ["A[8]", "Amt[3]", "Y[8]"],
          [[b(x, 8), b(n, 3), b((x << n) | (x >> (8 - n)), 8)] for x, n in shifts])
    write("RotateRight8", ["A[8]", "Amt[3]", "Y[8]"],
          [[b(x, 8), b(n, 3), b((x >> n) | (x << (8 - n)), 8)] for x, n in shifts])
    write("ALUCore8", ["A[8]", "B[8]", "Op[4]", "R[8]", "Z", "C", "S", "V"],
          [[b(x, 8), b(y, 8), b(op, 4), b(r, 8), str(z), str(c), str(sg), str(v)]
           for op in range(16) for x, y in ALU_PAIRS + pairs()[::35]
           for r, z, c, sg, v in [alu(op, x, y)]])
    # Register8bit is sequential: rows run in order and state carries over.
    rows, q = [], 0
    rng = random.Random(7)
    for d in EDGES + [rng.randrange(256) for _ in range(50)]:
        load = rng.randrange(2)
        rows.append(["1" if load else "0", b(d, 8), "0", b(q, 8)])
        if load:
            q = d
        rows.append(["1" if load else "0", b(d, 8), "1", b(q, 8)])
    write("Register8bit", ["Load", "D[8]", "CLK", "Q[8]"], rows, sequential=True)
    hexseg = ["1111110", "0110000", "1101101", "1111001", "0110011", "1011011", "1011111", "1110000",
              "1111111", "1111011", "1110111", "0011111", "1001110", "0111101", "1001111", "1000111"]
    write("HexDecoder7", ["In[4]", "a", "b", "c", "d", "e", "f", "g"],
          [[b(v, 4)] + list(hexseg[v]) for v in range(16)])
    write("Add3", ["In[4]", "Out[4]"], [[b(v, 4), b(v + 3 if v >= 5 else v, 4)] for v in range(16)])
    write("BinToBCD8", ["In[8]", "Hundreds[4]", "Tens[4]", "Ones[4]"],
          [[b(v, 8), b(v // 100, 4), b(v // 10 % 10, 4), b(v % 10, 4)] for v in range(256)])
    write("RegFile4x8", ["D[8]", "WSel[2]", "WE", "RSelA[2]", "RSelB[2]", "CLK", "Reset",
                         "QA[8]", "QB[8]", "R0[8]", "R1[8]", "R2[8]", "R3[8]"], regfile_rows(), sequential=True)
    write("PC8", ["D[8]", "Jump", "Hold", "CLK", "Reset", "Q[8]"], pc_rows(), sequential=True)
    write("Decoder16", ["Instr[16]", "Z", "C", "AluOp[4]", "RegWrite", "WSrc[2]", "Jump", "FlagWrite",
                        "OutWrite", "Halt"],
          [[b(i, 16), str(z), str(c)] + [b(v, w) for v, w in zip(decode(i, z, c), (4, 1, 2, 1, 1, 1, 1))]
           for i in decoder_instrs() for z in (0, 1) for c in (0, 1)])
    write("cpu", ["tick", "Reset", "PC[8]", "R0[8]", "R1[8]", "R2[8]", "R3[8]", "Out[8]", "Z", "C", "Halt"],
          cpu_rows(), sequential=True)
    write("ControlUnit", ["CLK", "Reset", "Load", "Execute", "LoadAB", "LoadOut", "S0", "S1"],
          controlunit_rows(), sequential=True)
    write("main", ["tick", "Reset", "Load", "Execute", "A[8]", "B[8]", "Op[4]",
                   "R[8]", "Z", "C", "S", "V", "S0", "S1", "Dec[12]"], main_rows(), sequential=True)


def regfile_rows():
    rng = random.Random(21)
    regs, rows = [0] * 4, []
    steps = [(1, 0, 0, 0, 0, 0)] + [(0, rng.randrange(256), rng.randrange(4), rng.randrange(2),
                                     rng.randrange(4), rng.randrange(4)) for _ in range(150)]
    steps += [(1, 77, 2, 1, 2, 3), (0, 9, 1, 0, 1, 2)]
    for reset, d, ws, we, ra, rb in steps:
        for clk in (0, 1):
            if clk:
                if reset:
                    regs = [0] * 4
                elif we:
                    regs[ws] = d
            rows.append([b(d, 8), b(ws, 2), str(we), b(ra, 2), b(rb, 2), str(clk), str(reset),
                         b(regs[ra], 8), b(regs[rb], 8)] + [b(r, 8) for r in regs])
    return rows


def pc_rows():
    rng = random.Random(22)
    q, rows = 0, []
    steps = [(0, 0, 0, 1)] + [(rng.randrange(256), int(rng.random() < 0.3), int(rng.random() < 0.2),
                                int(rng.random() < 0.05)) for _ in range(200)]
    steps += [(0, 0, 0, 0)] * 3 + [(0, 0, 0, 1)] + [(5, 1, 1, 0)]  # Hold beats Jump
    for d, jump, hold, reset in steps:
        for clk in (0, 1):
            if clk:
                q = 0 if reset else q if hold else d if jump else (q + 1) & 0xFF
            rows.append([b(d, 8), str(jump), str(hold), str(clk), str(reset), b(q, 8)])
    return rows


def decode(instr, z, c):
    """Decoder16 model: (AluOp, RegWrite, WSrc, Jump, FlagWrite, OutWrite, Halt)."""
    op = instr >> 12
    jump = op == 3 or (op == 4 and z) or (op == 5 and not z) or (op == 6 and c)
    return (instr & 15, int(op in (0, 1, 2)), {1: 1, 2: 2}.get(op, 0), int(jump), int(op == 0),
            int(op == 7), int(op == 8))


def decoder_instrs():
    rng = random.Random(23)
    return [op << 12 | rng.randrange(4096) for op in range(16) for _ in range(6)] + [0, 0xFFFF]


def cpu_program():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from asm import assemble
    return assemble(open(os.path.join(ROOT, "programs", "fibonacci.asm")).read())


def cpu_step(rom, st, reset):
    """One clock tick of the single-cycle CPU. st = dict(pc, regs, out, z, c)."""
    if reset:
        return dict(pc=0, regs=[0] * 4, out=0, z=0, c=0)
    st = dict(st, regs=list(st["regs"]))
    instr = rom[st["pc"]] if st["pc"] < len(rom) else 0
    op, rd, rs, imm = instr >> 12, (instr >> 10) & 3, (instr >> 8) & 3, instr & 0xFF
    a, bb = st["regs"][rd], st["regs"][rs]
    _alu, regwrite, wsrc, jump, flagwrite, outwrite, halt = decode(instr, st["z"], st["c"])
    r, z, c, _s, _v = alu(instr & 15, a, bb)
    if regwrite:
        st["regs"][rd] = [r, imm, bb][wsrc]
    if flagwrite:
        st["z"], st["c"] = z, c
    if outwrite:
        st["out"] = bb
    if not halt:
        st["pc"] = imm if jump else (st["pc"] + 1) & 0xFF
    return st


def cpu_rows():
    """Run the ROM program (programs/fibonacci.asm) from Reset until well after HALT."""
    rom, rows = cpu_program(), []
    st = dict(pc=0, regs=[0] * 4, out=0, z=0, c=0)
    for t in range(140):
        reset = int(t == 0 or t == 120)
        st = cpu_step(rom, st, reset)
        halt = int(st["pc"] < len(rom) and rom[st["pc"]] >> 12 == 8)
        rows.append(["1", str(reset), b(st["pc"], 8)] + [b(r, 8) for r in st["regs"]]
                    + [b(st["out"], 8), str(st["z"]), str(st["c"]), str(halt)])
    return rows


def fsm_next(state, reset, load, execute):
    """ControlUnit next state: IDLE 0 -Load-> LOAD 1 -> EXECUTE 2 -Execute-> DISPLAY 3 -> IDLE."""
    if reset:
        return 0
    return {0: 1 if load else 0, 1: 2, 2: 3 if execute else 2, 3: 0}[state]


def controlunit_rows():
    rng = random.Random(11)
    rows, state = [], 0
    steps = [(r, l, e) for r in (0, 1) for l in (0, 1) for e in (0, 1)] * 4
    steps += [(int(rng.random() < 0.1), rng.randrange(2), rng.randrange(2)) for _ in range(200)]
    for reset, load, execute in steps:
        for clk in (0, 1):
            if clk:
                state = fsm_next(state, reset, load, execute)
            rows.append([str(clk), str(reset), str(load), str(execute),
                         str(int(state == 1)), str(int(state == 2)), str(state & 1), str(state >> 1)])
    return rows


def dec(v):
    """Three decimal digits side by side, 4 bits each (hundreds, tens, ones)."""
    return (v // 100) << 8 | (v // 10 % 10) << 4 | v % 10


def main_rows():
    """Whole system, one clock cycle per row. Registers latch on the same edge as the FSM."""
    rng = random.Random(12)
    rows = []
    state = qa = qb = out = 0
    flags = (0, 0, 0, 0)

    def step(reset, load, execute, x, y, op):
        nonlocal state, qa, qb, out, flags
        if state == 1:
            qa, qb = x, y
        if state == 2:
            r, z, c, sg, v = alu(op, qa, qb)
            out, flags = r, (z, c, sg, v)
        state = fsm_next(state, reset, load, execute)
        rows.append(["1", str(reset), str(load), str(execute), b(x, 8), b(y, 8), b(op, 4), b(out, 8)]
                    + [str(f) for f in flags] + [str(state & 1), str(state >> 1), b(dec(out), 12)])

    step(1, 0, 0, 0, 0, 0)
    for op in range(16):
        for x, y in ALU_PAIRS[:6]:
            step(0, 1, 0, x, y, op)        # IDLE -> LOAD
            step(0, 0, 0, x, y, op)        # LOAD -> EXECUTE, A and B latched
            step(0, 0, 1, 0, 0, op)        # EXECUTE -> DISPLAY, result latched
            step(0, 0, 0, 0, 0, op)        # DISPLAY -> IDLE
    for _ in range(150):                   # random button presses, including Reset
        step(int(rng.random() < 0.05), rng.randrange(2), rng.randrange(2),
             rng.randrange(256), rng.randrange(256), rng.randrange(16))
    return rows


if __name__ == "__main__":
    main()
