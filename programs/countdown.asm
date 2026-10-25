; Counts down from 10 to 0 on the display.
        LDI R0, 10
        LDI R1, 1
loop:   OUT R0
        SUB R0, R1      ; R0 = R0 - 1, Z = 1 when it reaches 0
        JNZ loop
        OUT R0          ; show the 0
        HALT
