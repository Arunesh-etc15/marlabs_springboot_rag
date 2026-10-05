package com.marlabs.policy;

import java.io.IOException;
import java.time.LocalDate;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import static com.marlabs.policy.ApiModels.*;

@Service
public class BatchService {
    private static final Logger log = LoggerFactory.getLogger(BatchService.class);
    private final PythonGateway python;
    private final ResponseValidator responses;
    public BatchService(PythonGateway python, ResponseValidator responses) {
        this.python = python;
        this.responses = responses;
    }
    public BatchResponse process(Caller caller, LocalDate date, BatchMetadata metadata,
                                 List<MultipartFile> files) {
        Map<String, MultipartFile> uploads = validate(metadata, files);
        List<ItemResult> results = new ArrayList<>();
        List<byte[]> previousBytes = new ArrayList<>();
        List<String> previousIds = new ArrayList<>();
        for (ManifestEntry entry : metadata.documents()) {
            String duplicate = null;
            try {
                byte[] bytes = uploads.get(entry.filename()).getBytes();
                // Compare bytes directly so exact-duplicate detection does not depend on a hash.
                for (int i = 0; i < previousBytes.size(); i++) {
                    if (Arrays.equals(bytes, previousBytes.get(i))) {
                        duplicate = previousIds.get(i);
                        break;
                    }
                }
                previousBytes.add(bytes);
                previousIds.add(entry.documentId());
                if (bytes.length == 0) throw ApiException.invalid("The uploaded file is empty.");
                if (!entry.filename().toLowerCase(Locale.ROOT).matches(".*\\.(txt|pdf)$")) {
                    throw new ApiException(org.springframework.http.HttpStatus.BAD_REQUEST,
                            "UNSUPPORTED_FILE", "Only UTF-8 TXT and text-based PDF files are supported.");
                }
                DocumentAnalysis analysis = python.analyze(caller, date, metadata.batchId(),
                        entry.documentId(), entry.filename(), bytes);
                responses.analysis(analysis, caller, date);
                List<String> issues = new ArrayList<>(analysis.issues());
                issues.add("Human review is required; this report does not approve payment.");
                results.add(new ItemResult(entry.documentId(), ProcessingStatus.COMPLETED,
                        analysis.extracted(), analysis.fieldEvidence(), analysis.policy(), true,
                        List.copyOf(issues), duplicate, null));
            } catch (IOException ex) {
                results.add(failed(entry, duplicate, "UNREADABLE_FILE", "The uploaded file could not be read."));
            } catch (ApiException ex) {
                String code = ex.code().equals("INVALID_REQUEST") ? "EMPTY_FILE" : ex.code();
                results.add(failed(entry, duplicate, code, ex.getMessage()));
            }
            ItemResult result = results.get(results.size() - 1);
            log.info("batch={} document={} status={} error={}", safeId(metadata.batchId()),
                    safeId(entry.documentId()), result.processingStatus(),
                    result.error() == null ? "none" : result.error().code());
        }
        int completed = (int) results.stream().filter(r -> r.processingStatus() == ProcessingStatus.COMPLETED).count();
        return new BatchResponse(metadata.batchId(),
                new Summary(results.size(), completed, results.size() - completed), List.copyOf(results));
    }
    private Map<String, MultipartFile> validate(BatchMetadata metadata, List<MultipartFile> files) {
        Set<String> ids = new HashSet<>();
        Set<String> names = new HashSet<>();
        for (ManifestEntry entry : metadata.documents()) {
            if (!ids.add(entry.documentId()) || !names.add(entry.filename())) {
                throw ApiException.invalid("Manifest document_id and filename values must be unique.");
            }
        }
        Map<String, MultipartFile> uploads = new HashMap<>();
        for (MultipartFile file : files) {
            String name = file.getOriginalFilename();
            if (name == null || !names.contains(name) || uploads.putIfAbsent(name, file) != null) {
                throw ApiException.invalid("Each file must match exactly one manifest filename.");
            }
        }
        if (uploads.size() != names.size()) {
            throw ApiException.invalid("Every manifest entry requires one file.");
        }
        return uploads;
    }
    private ItemResult failed(ManifestEntry entry, String duplicate, String code, String message) {
        return new ItemResult(entry.documentId(), ProcessingStatus.FAILED, null, Map.of(), null,
                true, List.of("Processing failed; human review is required."), duplicate, new ApiError(code, message));
    }
    private String safeId(String id) {
        return id.replaceAll("[\\r\\n\\t]", "_");
    }
}
