import com.cburch.logisim.circuit.Circuit;
import com.cburch.logisim.circuit.CircuitState;
import com.cburch.logisim.comp.Component;
import com.cburch.logisim.data.BitWidth;
import com.cburch.logisim.data.Value;
import com.cburch.logisim.file.Loader;
import com.cburch.logisim.file.LogisimFile;
import com.cburch.logisim.instance.Instance;
import com.cburch.logisim.instance.InstanceComponent;
import com.cburch.logisim.instance.StdAttr;
import com.cburch.logisim.proj.Project;
import com.cburch.logisim.std.wiring.Pin;
import java.io.File;
import java.nio.file.Files;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Sequential test-vector runner. Logisim 4.0.0's own --test-vector starts every
 * row from a fresh state, so clocked blocks can't be tested with it. This keeps
 * one simulation state for the whole file: rows are applied in order, the
 * circuit is propagated, then outputs are compared. Same file format as
 * Logisim's (header "Name[width] ...", binary values, '#' comments), plus 'x'
 * digits in expected outputs mean "don't care". A column named "tick" is not a
 * pin: a 1 there runs one full cycle of the circuit's Clock components after
 * the inputs are applied (for top-level circuits like main).
 *
 * Usage: SeqTest <circ_file> <circuit_name> <vector_file>
 */
public class SeqTest {
  public static void main(String[] args) throws Exception {
    LogisimFile file = new Loader(null).openLogisimFile(new File(args[0]));
    Project proj = new Project(file);
    Circuit circ = file.getCircuit(args[1]);
    CircuitState state = CircuitState.createRootState(proj, circ);
    Map<String, Instance> pins = new HashMap<>();
    for (Component c : circ.getNonWires()) {
      if (c.getFactory() instanceof Pin && c instanceof InstanceComponent ic) {
        pins.put(c.getAttributeSet().getValue(StdAttr.LABEL), ic.getInstance());
      }
    }
    List<String> lines = Files.readAllLines(new File(args[2]).toPath()).stream()
        .map(String::trim).filter(l -> !l.isEmpty() && !l.startsWith("#")).toList();
    String[] header = lines.get(0).split("\\s+");
    String[] names = new String[header.length];
    for (int i = 0; i < header.length; i++) {
      names[i] = header[i].replaceAll("\\[.*", "");
      if (!names[i].equals("tick") && !pins.containsKey(names[i])) throw new IllegalArgumentException("no pin " + names[i]);
    }
    int passed = 0, failed = 0;
    for (int row = 1; row < lines.size(); row++) {
      String[] vals = lines.get(row).split("\\s+");
      boolean tick = false;
      for (int i = 0; i < names.length; i++) {
        if (names[i].equals("tick")) {
          tick = vals[i].equals("1");
          continue;
        }
        Instance pin = pins.get(names[i]);
        if (!Pin.FACTORY.isInputPin(pin)) continue;
        BitWidth w = pin.getAttributeValue(StdAttr.WIDTH);
        Pin.FACTORY.driveInputPin(state.getInstanceState(pin),
            Value.createKnown(w, Long.parseLong(vals[i], 2)));
        state.markComponentAsDirty(pin.getComponent());
      }
      state.getPropagator().propagate();
      for (int k = 0; tick && k < 2; k++) {
        state.getPropagator().toggleClocks();
        state.getPropagator().propagate();
      }
      StringBuilder err = new StringBuilder();
      for (int i = 0; i < names.length; i++) {
        Instance pin = pins.get(names[i]);
        if (pin == null || Pin.FACTORY.isInputPin(pin)) continue;
        String got = Pin.FACTORY.getValue(state.getInstanceState(pin)).toBinaryString();
        String want = vals[i];
        boolean ok = got.length() == want.length();
        for (int k = 0; ok && k < want.length(); k++) {
          ok = want.charAt(k) == 'x' || want.charAt(k) == got.charAt(k);
        }
        if (!ok) err.append("  ").append(names[i]).append(" = ").append(got)
            .append(" (expected ").append(want).append(")\n");
      }
      if (err.length() == 0) {
        passed++;
      } else {
        failed++;
        if (failed <= 10) System.out.print("Error on test vector " + row + ":\n" + err);
      }
    }
    System.out.println("Passed: " + passed + ", Failed: " + failed);
    System.exit(failed == 0 ? 0 : 1);
  }
}
