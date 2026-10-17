# What was wrong with v1

Notes from reviewing the original 4-bit circuit (`v1/ALU.circ`) before building v2.

## Port order

In Logisim Evolution's default appearance, a subcircuit's inputs are on the
left and outputs on the right, each side sorted by the pin's **(y, x)**
position inside the subcircuit. Pins that share a y are sorted by x, so in v1
several blocks ended up with scrambled port orders:

| Subcircuit | Inputs (top to bottom) | Outputs (top to bottom) |
|---|---|---|
| Adder4bit, Subtractor4bit | A1, A3, A2, B1, B3, B2, A0, B0, (Cin) | S1, S2, S0, S3, Cout |
| INC4bit, DEC4bit | A1, A3, A2, A0 | S1, S2, S0, S3, Cout |
| ALUCore | A0, A2, A3, A1, B0..B3, Op0..Op3 | Cout, R0..R3 |
| SevenSegment | R3, R2, R1, R0 | a, b, c, e, d, f, g |

The wiring in `main` matched these orders, so v1 worked, but reusing the
blocks was a trap. In v2 every block puts its pins at separate heights in a
fixed order, and 8-bit values use a single bus pin.

## Bugs and inconsistencies

1. **Carry flag.** The C LED was wired to the ADD adder's carry only, whatever
   the opcode, and it skipped the output register while Z and S went through it.
2. **Control unit clock.** `ControlUnit` had its own Clock component and no CLK
   input, and the register loads came straight from the Load/Execute buttons,
   so the FSM tracked state without controlling anything.
3. **NOT on 1xxx.** The circuit used Op3 with 2:1 muxes, so all 8 codes 1xxx gave NOT.
4. **Division by zero** was documented as undefined but actually gave Q = 0,
   R = A, because each step only subtracts when B ≠ 0.
5. **Remainder never left DIV4bit.** Only the quotient reached the result mux.
6. **Unused block.** `DivStep` was an older version left in the file.
7. **Seven-segment decoder** lit the wrong segments for 6, 7, d and E.
8. **Opcode mux** used Logisim's built-in Multiplexer instead of gates.

All of these are fixed in v2.
