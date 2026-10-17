import com.cburch.logisim.circuit.Circuit;
import com.cburch.logisim.circuit.SubcircuitFactory;
import com.cburch.logisim.comp.Component;
import com.cburch.logisim.comp.EndData;
import com.cburch.logisim.data.Direction;
import com.cburch.logisim.data.Location;
import com.cburch.logisim.file.Loader;
import com.cburch.logisim.file.LogisimFile;
import com.cburch.logisim.instance.Instance;
import com.cburch.logisim.instance.StdAttr;
import java.io.File;
import java.util.Map;

/**
 * Loads a .circ file with Logisim itself and prints, as tab-separated lines,
 * the real location of every component end, so the generator never has to
 * guess coordinates.
 *
 * END  circuit  factory  compX,compY  label  endIndex  x,y  width  i|o|io
 * PORT circuit  factory  compX,compY  pinLabel  x,y
 */
public class Probe {
  private static String label(Component comp) {
    var attrs = comp.getAttributeSet();
    return attrs.containsAttribute(StdAttr.LABEL) ? attrs.getValue(StdAttr.LABEL) : "";
  }

  public static void main(String[] args) throws Exception {
    LogisimFile file = new Loader(null).openLogisimFile(new File(args[0]));
    StringBuilder out = new StringBuilder();
    for (Circuit circ : file.getCircuits()) {
      for (Component comp : circ.getNonWires()) {
        Location loc = comp.getLocation();
        String head = circ.getName() + "\t" + comp.getFactory().getName() + "\t"
            + loc.getX() + "," + loc.getY();
        int i = 0;
        for (EndData end : comp.getEnds()) {
          Location e = end.getLocation();
          out.append("END\t").append(head).append('\t').append(label(comp)).append('\t')
              .append(i++).append('\t').append(e.getX()).append(',').append(e.getY()).append('\t')
              .append(end.getWidth().getWidth()).append('\t')
              .append(end.isInput() ? "i" : "").append(end.isOutput() ? "o" : "").append('\n');
        }
        if (comp.getFactory() instanceof SubcircuitFactory sub) {
          Map<Location, Instance> ports =
              sub.getSubcircuit().getAppearance().getPortOffsets(Direction.EAST);
          for (var p : ports.entrySet()) {
            Location e = loc.translate(p.getKey().getX(), p.getKey().getY());
            out.append("PORT\t").append(head).append('\t')
                .append(p.getValue().getAttributeValue(StdAttr.LABEL)).append('\t')
                .append(e.getX()).append(',').append(e.getY()).append('\n');
          }
        }
      }
    }
    System.out.print(out);
    System.exit(0);
  }
}
