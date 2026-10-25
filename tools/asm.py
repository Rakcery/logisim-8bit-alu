#!/usr/bin/env python3
"""Assembler for the mini CPU in ALU.circ (circuit `cpu`).

Instruction word (16 bits): op[15:12] rd[11:10] rs[9:8] imm[7:0]

    ADD rd, rs   (and SUB INC DEC DIV AND OR XOR NOT MOD MUL SHL SHR SAR ROL ROR)
                 rd = rd <op> rs, flags Z and C are updated. imm[3:0] holds the ALU opcode.
    LDI rd, n    rd = n (0..255)
    MOV rd, rs   rd = rs
    JMP label    jump
    JZ  label    jump if Z = 1
    JNZ label    jump if Z = 0
    JC  label    jump if C = 1
    OUT rs       show rs on the display
    HALT         stop

Labels end with ':'; ';' starts a comment.

Usage:
    python3 tools/asm.py programs/countdown.asm            # writes programs/countdown.hex
    python3 tools/asm.py programs/countdown.asm ALU.circ   # also loads it into the cpu's ROM
The .hex file can be loaded in Logisim: right-click the ROM in `cpu` > Load Image.
"""
import re
import sys

ALU_OPS = ["ADD", "SUB", "INC", "DEC", "DIV", "AND", "OR", "XOR",
           "NOT", "MOD", "MUL", "SHL", "SHR", "SAR", "ROL", "ROR"]
OPCODES = {"LDI": 1, "MOV": 2, "JMP": 3, "JZ": 4, "JNZ": 5, "JC": 6, "OUT": 7, "HALT": 8}


def reg(tok):
    m = re.fullmatch(r"R([0-3])", tok.upper())
    if not m:
        raise ValueError(f"expected a register R0..R3, got {tok!r}")
    return int(m.group(1))


def assemble(text):
    """Return the program as a list of 16-bit words."""
    lines, labels = [], {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split(";")[0].strip()
        while ":" in line:
            label, line = line.split(":", 1)
            labels[label.strip()] = len(lines)
            line = line.strip()
        if line:
            lines.append((n, line))
    words = []
    for n, line in lines:
        name, *rest = line.replace(",", " ").split()
        name = name.upper()
        try:
            if name in ALU_OPS:
                rd, rs = (reg(rest[0]), reg(rest[1])) if len(rest) > 1 else (reg(rest[0]), 0)
                words.append(rd << 10 | rs << 8 | ALU_OPS.index(name))
            elif name == "LDI":
                v = int(rest[1], 0)
                if not 0 <= v <= 255:
                    raise ValueError("value must be 0..255")
                words.append(1 << 12 | reg(rest[0]) << 10 | v)
            elif name == "MOV":
                words.append(2 << 12 | reg(rest[0]) << 10 | reg(rest[1]) << 8)
            elif name in ("JMP", "JZ", "JNZ", "JC"):
                target = labels[rest[0]] if rest[0] in labels else int(rest[0], 0)
                words.append(OPCODES[name] << 12 | target)
            elif name == "OUT":
                words.append(7 << 12 | reg(rest[0]) << 8)
            elif name == "HALT":
                words.append(8 << 12)
            else:
                raise ValueError(f"unknown instruction {name}")
        except (IndexError, KeyError, ValueError) as e:
            raise SystemExit(f"line {n}: {line}: {e}")
    if len(words) > 256:
        raise SystemExit("program is longer than 256 instructions")
    return words


def rom_contents(words):
    """The text Logisim stores in a ROM's `contents` attribute (8-bit address, 16-bit data)."""
    rows = [" ".join(f"{w:x}" for w in words[i:i + 8]) for i in range(0, len(words), 8)]
    return "addr/data: 8 16\n" + "\n".join(rows) + "\n"


def main():
    src = sys.argv[1]
    words = assemble(open(src).read())
    out = re.sub(r"\.asm$", "", src) + ".hex"
    with open(out, "w") as f:
        f.write("v2.0 raw\n" + rom_contents(words).split("\n", 1)[1])
    print(f"{len(words)} instructions -> {out}")
    if len(sys.argv) > 2:
        circ = sys.argv[2]
        s = open(circ).read()
        # Logisim saves the contents as element text, tools/gen_blocks.py as a val attribute.
        text = rom_contents(words)
        new, n = re.subn(r'(<a name="contents">)addr/data: 8 16\n[^<]*(</a>)',
                         lambda m: m.group(1) + text + m.group(2), s)
        if n == 0:
            new, n = re.subn(r'(<a name="contents" val=")addr/data: 8 16&#10;[^"]*(")',
                             lambda m: m.group(1) + text.replace("\n", "&#10;") + m.group(2), s)
        if n != 1:
            raise SystemExit(f"expected one ROM in {circ}, found {n}")
        open(circ, "w").write(new)
        print(f"loaded into the ROM of {circ}")


if __name__ == "__main__":
    main()
