package com.marlabs.policy;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

public final class ApiModels {
    private ApiModels() {}
    public record Caller(String tenant, String role) {}
    public record AnswerRequest(@NotBlank String question, @NotBlank String asOf) {}
    public record ManifestEntry(@NotBlank String documentId, @NotBlank String filename) {}
    public record BatchMetadata(@NotBlank String batchId, @NotBlank String asOf,
                                @NotEmpty List<@NotNull @Valid ManifestEntry> documents) {}
    public enum Outcome { ANSWERED, INSUFFICIENT_EVIDENCE, CONFLICT }
    public record Citation(String chunkId, String quote) {}
    public record AnswerResponse(Outcome status, String answer, List<Citation> citations) {}
    public record Extracted(String benefit, BigDecimal amount, String currency, String reference) {}
    public record DocumentAnalysis(Extracted extracted, Map<String, List<String>> fieldEvidence,
                                   AnswerResponse policy, List<String> issues) {}
    public record ApiError(String code, String message) {}
    public enum ProcessingStatus { COMPLETED, FAILED }
    public record ItemResult(String documentId, ProcessingStatus processingStatus, Extracted extracted,
                             Map<String, List<String>> fieldEvidence, AnswerResponse policy,
                             boolean reviewRequired, List<String> issues, String duplicateOf, ApiError error) {}
    public record Summary(int total, int completed, int failed) {}
    public record BatchResponse(String batchId, Summary summary, List<ItemResult> results) {}
}
