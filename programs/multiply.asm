; 7 x 6 by adding 7 six times. The MUL instruction does it in one step;
; this shows how a loop works.
        LDI R0, 0       ; total
        LDI R1, 7       ; number to add
        LDI R2, 6       ; how many times
        LDI R3, 1
loop:   ADD R0, R1
        SUB R2, R3      ; one fewer to go, Z = 1 when done
        JNZ loop
        OUT R0          ; 42
        HALT
