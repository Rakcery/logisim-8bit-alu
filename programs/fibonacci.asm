; Fibonacci numbers on the display: 0 1 1 2 3 5 8 13 ... 233, then stop.
        LDI R0, 0
        LDI R1, 1
loop:   OUT R0          ; show the current number
        MOV R2, R0
        ADD R2, R1      ; R2 = R0 + R1, C = 1 if it went past 255
        JC  done
        MOV R0, R1
        MOV R1, R2
        JMP loop
done:   OUT R1          ; last one that fits: 233
        HALT
