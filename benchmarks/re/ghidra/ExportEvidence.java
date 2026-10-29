// Export static analysis facts only. Does not execute the target binary.
// @category DACN.Benchmark
import ghidra.app.util.headless.HeadlessScript;
import ghidra.framework.Application;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

public class ExportEvidence extends HeadlessScript {
    @Override public void run() throws Exception {
        if (getScriptArgs().length != 1) throw new IllegalArgumentException("Expected output JSON path");
        JsonObject result = new JsonObject();
        result.addProperty("producer", "Ghidra headless");
        result.addProperty("ghidra_version", Application.getApplicationVersion());
        result.addProperty("java_version", System.getProperty("java.version"));
        result.addProperty("binary_sha256", currentProgram.getExecutableSHA256());
        result.addProperty("program", currentProgram.getName());
        result.addProperty("language", currentProgram.getLanguageID().toString());
        result.addProperty("image_base", currentProgram.getImageBase().toString());
        result.addProperty("analysis_timed_out", analysisTimeoutOccurred());
        result.addProperty("target_executed", false);
        JsonArray functions = new JsonArray();
        FunctionIterator fi = currentProgram.getFunctionManager().getFunctions(true);
        while (fi.hasNext()) {
            monitor.checkCancelled();
            Function f = fi.next(); JsonObject row = new JsonObject();
            row.addProperty("name", f.getName()); row.addProperty("entry_va", f.getEntryPoint().toString());
            row.addProperty("is_thunk", f.isThunk()); functions.add(row);
        }
        result.add("functions", functions);
        JsonArray imports = new JsonArray();
        SymbolIterator si = currentProgram.getSymbolTable().getExternalSymbols();
        while (si.hasNext()) {
            Symbol s = si.next(); JsonObject row = new JsonObject();
            row.addProperty("name", s.getName()); row.addProperty("namespace", s.getParentNamespace().getName());
            row.addProperty("external_address", s.getAddress().toString()); imports.add(row);
        }
        result.add("external_symbols", imports);
        JsonArray strings = new JsonArray();
        DataIterator di = currentProgram.getListing().getDefinedData(true);
        while (di.hasNext()) {
            Data d = di.next(); Object value = d.getValue();
            if (value instanceof String) {
                JsonObject row = new JsonObject(); row.addProperty("value", (String)value);
                row.addProperty("va", d.getAddress().toString()); strings.add(row);
            }
        }
        result.add("defined_strings", strings);
        result.addProperty("limitations", "Static facts only; not malware labels, decompiler validation, REA output or D.0 ToolResult. External addresses are not IAT addresses.");
        Files.writeString(Path.of(getScriptArgs()[0]), new GsonBuilder().setPrettyPrinting().create().toJson(result), StandardCharsets.UTF_8);
        println("DACN_EVIDENCE_EXPORTED " + getScriptArgs()[0]);
    }
}
