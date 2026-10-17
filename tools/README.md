# tools/

Scripts that generate the repetitive subcircuits of `ALU.circ`.
Requirements: Python 3.9+, a JDK (for `javac`), and on Linux without a display `xvfb-run`.

```bash
JAR=$(tools/get_logisim.sh)                 # Logisim Evolution 4.0.0
python3 tools/gen_blocks.py ALU.circ "$JAR"  # rebuild the scripted blocks in place
python3 tests/gen_vectors.py                 # rebuild expected results
python3 tests/run_tests.py "$JAR"            # run every block's vectors in Logisim
python3 tools/circ_ports.py ALU.circ         # print port order of every subcircuit
```

| File | What it does |
|---|---|
| `bootstrap_v2.py` | One-off: built the initial v2 `ALU.circ` from `v1/ALU.circ` (header + reused v1 blocks + empty `main`). |
| `gen_blocks.py` | Block definitions (components + named nets). Replaces only the circuits it owns; hand-drawn circuits are untouched. |
| `circgen.py` | Layout, XML writing, and the probe-based connection step. |
| `probe/Probe.java` | Loads a `.circ` with Logisim and prints the real location of every port, so no coordinate is guessed. |
| `probe/SeqTest.java` | Sequential test-vector runner (Logisim 4.0.0's `--test-vector` resets state on every row). |
| `circ_ports.py` | Prints each subcircuit's port order (inputs left, outputs right, sorted by pin (y, x)). |

## How the scripted blocks are wired

The scripted blocks contain no wires. Every connection is a Tunnel named after its
net, placed exactly on the port location that Logisim reports. After writing,
the file is probed again and the generator fails if a net has fewer than two
ports, mixed widths, or if two component ports overlap by accident.
