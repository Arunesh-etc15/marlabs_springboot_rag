package com.marlabs.policy;

import java.io.IOException;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import java.util.regex.Pattern;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.text.PDFTextStripper;

/** Reads numbered source records directly from the same PDF used by Python. */
final class PolicyPdfSource {
    private static final Pattern HEADER = Pattern.compile(
            "^[ \\t]*[0-9]+\\.[ \\t]+([A-Za-z0-9_-]+)[ \\t]*$", Pattern.MULTILINE);
    private static final Pattern METADATA = Pattern.compile(
            "([^|]+)\\|([^|]+)\\|\\s*(Approved|Draft)\\s*\\|\\s*"
            + "([0-9]{4}-[0-9]{2}-[0-9]{2})\\s+to\\s+([0-9]{4}-[0-9]{2}-[0-9]{2})");
    private static final Pattern INJECTION = Pattern.compile(
            "system\\s+message|ignore\\s+(?:all\\s+)?(?:prior\\s+)?rules|ignore\\s+(?:the\\s+)?caller"
            + "|prompt[- ]injection|not\\s+policy", Pattern.CASE_INSENSITIVE);

    static List<ResponseValidator.Policy> load(Path path) throws IOException {
        if (!path.toString().toLowerCase(java.util.Locale.ROOT).endsWith(".pdf")) {
            throw new IllegalArgumentException("POLICY_FILE must point to a policy PDF, not JSON.");
        }
        try (var document = Loader.loadPDF(path.toFile())) {
            if (document.isEncrypted()) {
                throw new IllegalArgumentException("The policy PDF must not be encrypted.");
            }
            var stripper = new PDFTextStripper();
            stripper.setLineSeparator("\n");
            stripper.setPageEnd("\n");
            return parse(stripper.getText(document));
        }
    }

    static List<ResponseValidator.Policy> parse(String source) {
        String text = source.replace("\r\n", "\n").replace('\r', '\n');
        var headers = new ArrayList<java.util.regex.MatchResult>();
        var matcher = HEADER.matcher(text);
        while (matcher.find()) headers.add(matcher.toMatchResult());
        if (headers.isEmpty() || !text.substring(0, headers.get(0).start()).isBlank()) {
            throw new IllegalArgumentException("The PDF must contain numbered policy records with metadata.");
        }

        var policies = new TreeMap<String, ResponseValidator.Policy>();
        for (int index = 0; index < headers.size(); index++) {
            var header = headers.get(index);
            int end = index + 1 < headers.size() ? headers.get(index + 1).start() : text.length();
            String block = text.substring(header.end(), end).strip();
            String[] lines = block.split("\n", 2);
            var metadata = METADATA.matcher(lines[0].strip());
            if (!metadata.matches() || lines.length < 2) {
                throw new IllegalArgumentException("Missing or invalid policy metadata for " + header.group(1));
            }
            // Normalize layout wrapping, including policy text that crosses pages.
            String policyText = lines[1].strip().replaceAll("\\s+", " ");
            var policy = new ResponseValidator.Policy(
                    header.group(1), metadata.group(1).strip(), metadata.group(2).strip(),
                    metadata.group(3), LocalDate.parse(metadata.group(4)),
                    LocalDate.parse(metadata.group(5)), policyText);
            if (policy.tenant().isBlank() || policy.role().isBlank() || policy.text().isBlank()
                    || !policy.effectiveTo().isAfter(policy.effectiveFrom())) {
                throw new IllegalArgumentException("Invalid policy metadata or empty text.");
            }
            var previous = policies.putIfAbsent(policy.id(), policy);
            if (previous != null && !previous.equals(policy)) {
                throw new IllegalArgumentException("Policy IDs must not identify different records.");
            }
        }
        return List.copyOf(policies.values());
    }

    static boolean isEvidence(String text) {
        return !INJECTION.matcher(text).find();
    }
}
