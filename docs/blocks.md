# Blocks

These subcircuits are built by `tools/gen_blocks.py`. Everything else in
`ALU.circ` is drawn by hand or reused unchanged from v1.

| Block | Ports (in → out) | Built from | Test vectors |
|---|---|---|---|
| Adder8bit | A[8], B[8], Cin → S[8], Cout, V | 8× FullAdder (v1), V = C7 XOR C8 | 4392 (edge cases + random) |
| Subtractor8bit | A[8], B[8] → S[8], Cout, V | Adder8bit, 8× NOT, Cin = 1 | 2196 |
| INC8bit | A[8] → S[8], Cout, V | Adder8bit, B = 0x00, Cin = 1 | 256 (exhaustive) |
| DEC8bit | A[8] → S[8], Cout, V | Adder8bit, B = 0xFF, Cin = 0 | 256 (exhaustive) |
| Register8bit | Load, D[8], CLK → Q[8] | 2× Register4bit (v1) | 128 (sequential) |
| LogicUnit8 | A[8], B[8] → And[8], Or[8], Xor[8], NotA[8] | 8× AND/OR/XOR/NOT | 2196 |
| Select8bit | Sel, X[8], Y[8] → Out[8] | 8× Select1bit (v1); Sel=0 → X | 4392 |
| Comparator8bit | A[8], B[8] → GT, EQ, GTE | 2× Comparator4bitGTEQ (hand-drawn), low nibble cascades into high | 2196 |
| ZeroDetect8 | In[8] → Z | one 8-input NOR | 256 (exhaustive) |
| OpMux16x8 | Sel[4], In0[8] … In15[8] → Out[8] | 4→16 decoder (NOT + AND4) + 8× (16 AND2 + OR16) | 640 |
| OpMux16x2 | Sel[4], In0[2] … In15[2] → Out[2] | same structure, 2 bits wide (C and V) | 640 |
| DivStep8 | R[8], B[8], Qin[8] → N[8], Qout[8] | Comparator8bit, Subtractor8bit, Select8bit; q = (R ≥ B)·(B ≠ 0) | 2196 |
| DIV8bit | A[8], B[8] → Q[8], R[8], DZ | 8× DivStep8 (restoring), ZeroDetect8 on B; B = 0 → Q = 0, R = A, DZ = 1 | 2196 |
| MUL8bit | A[8], B[8] → Lo[8], Hi[8], Ovf | 64 AND partial products + 7× Adder8bit rows; Ovf = Hi ≠ 0 | 2196 |
| ShiftLeft8 | A[8], Amt[3] → Y[8], Cout | 3-stage barrel of Select1bit; Cout = last bit shifted out | 2048 (exhaustive) |
| ShiftRight8 | A[8], Amt[3], Arith → Y[8], Cout | same; Arith = 1 fills with A7 (SAR) | 4096 (exhaustive) |
| RotateLeft8 | A[8], Amt[3] → Y[8] | 3-stage barrel of Select1bit | 2048 (exhaustive) |
| RotateRight8 | A[8], Amt[3] → Y[8] | 3-stage barrel of Select1bit | 2048 (exhaustive) |
| ALUCore8 | A[8], B[8], Op[4] → R[8], Z, C, S, V | all operation blocks above → OpMux16x8 (R) and OpMux16x2 (C, V); Z = ZeroDetect8(R), S = R7; shift amount = B[2:0] | 1202 (all 16 opcodes × edge cases + random) |
| HexDecoder7 | In[4] → a, b, c, d, e, f, g | 4→16 decoder (NOT + AND4) + one OR per segment; hex digits 0–9, A, b, C, d, E, F | 16 (exhaustive) |
| ControlUnit | CLK, Reset, Load, Execute → LoadAB, LoadOut, S0, S1 | Moore FSM, 2× D flip-flop: IDLE 00 →(Load) LOAD 01 → EXECUTE 10 →(Execute) DISPLAY 11 → IDLE; synchronous Reset; LoadAB = LOAD, LoadOut = EXECUTE | 464 (sequential) |
| main | A[8], B[8], Op[4], Load, Execute, Reset → R[8], Z, C, S, V, S0, S1 | Clock, ControlUnit, RegisterA/B and OutputRegister (Register8bit), FlagRegister (Register4bit: Q0=Z, Q1=C, Q2=S, Q3=V), ALUCore8, 2× HexDecoder7 + 7-segment displays, flag and state LEDs; output pins mirror the displays for testing | 535 (sequential, clock ticks) |

Reused from v1 without changes: HalfAdder, FullAdder, Select1bit, Register4bit.
v1 SevenSegment was dropped from v2 (it lit the wrong segments for 6, 7, d and E); it is still in `v1/ALU.circ`.
Hand-drawn: Comparator4bitGTEQ (from v1 Comparator4bit, adds GTin/EQin cascade inputs; tested with all 1024 input combinations).
