package com.marlabs.policy;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static com.marlabs.policy.ApiModels.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class PublicApiTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @MockitoBean PythonGateway python;

    private AnswerResponse certification() {
        return new AnswerResponse(Outcome.ANSWERED, "The annual limit is INR 25000.",
                List.of(new Citation("atlas-cert-current",
                        "The annual certification reimbursement limit for employees is INR 25000.")));
    }
    private DocumentAnalysis analysis() {
        return new DocumentAnalysis(new Extracted("certification", new BigDecimal("18000"), "INR", "CERT-101"),
                Map.of("benefit", List.of("certification reimbursement"), "amount", List.of("INR 18000"),
                       "currency", List.of("INR 18000"), "reference", List.of("Reference: CERT-101")),
                certification(), List.of("Claims history is unavailable; remaining balance and payable amount are unknown."));
    }
    private MockMultipartFile metadata(String json) {
        return new MockMultipartFile("metadata", "", "application/json", json.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
    private MockMultipartFile file(String name, String body) {
        return new MockMultipartFile("files", name, "text/plain", body.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
    private String request(String date) {
        return "{\"question\":\"Certification limit?\",\"as_of\":\"" + date + "\"}";
    }

    @Test void answersUsingTrustedCallerContext() throws Exception {
        when(python.answer(any(), any(), anyString())).thenReturn(certification());
        mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01")
                .contentType("application/json").content(request("2026-09-21")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("ANSWERED"))
                .andExpect(jsonPath("$.citations[0].chunk_id").value("atlas-cert-current"));
        verify(python).answer(new Caller("Atlas", "employee"), LocalDate.of(2026,9,21), "Certification limit?");
    }
    @Test void missingAndUnknownCallersAreRejected() throws Exception {
        mvc.perform(post("/answer").contentType("application/json").content(request("2026-09-21")))
                .andExpect(status().isUnauthorized()).andExpect(jsonPath("$.code").value("INVALID_CALLER"));
        mvc.perform(post("/answer").header("X-Caller-Id", "unknown")
                .contentType("application/json").content(request("2026-09-21")))
                .andExpect(status().isUnauthorized());
        verifyNoInteractions(python);
    }
    @Test void validatesQuestionDatesAndRejectsBodyIdentityClaims() throws Exception {
        for (String date : List.of("2026-02-30", "2026-9-21", "not-a-date")) {
            mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01")
                    .contentType("application/json").content(request(date))).andExpect(status().isBadRequest());
        }
        mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01").contentType("application/json")
                .content("{\"question\":\"  \",\"as_of\":\"2026-09-21\"}")).andExpect(status().isBadRequest());
        mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01").contentType("application/json")
                .content("{\"question\":123,\"as_of\":\"2026-09-21\"}")).andExpect(status().isBadRequest());
        mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01").contentType("application/json")
                .content("{\"question\":\"limit\",\"as_of\":\"2026-09-21\",\"tenant\":\"Boreal\"}"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(python);
    }
    @Test void preservesInsufficientEvidenceAndConflicts() throws Exception {
        when(python.answer(any(), any(), anyString())).thenReturn(
                new AnswerResponse(Outcome.INSUFFICIENT_EVIDENCE, null, List.of()),
                new AnswerResponse(Outcome.CONFLICT, null, List.of(
                        new Citation("atlas-home-office-a", "The annual home-office allowance for employees is INR 12000."),
                        new Citation("atlas-home-office-b", "The annual home-office allowance for employees is INR 15000."))));
        mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01")
                .contentType("application/json").content(request("2026-09-21")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("INSUFFICIENT_EVIDENCE"))
                .andExpect(jsonPath("$.citations").isEmpty());
        mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01")
                .contentType("application/json").content(request("2026-09-21")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("CONFLICT"))
                .andExpect(jsonPath("$.citations.length()").value(2));
    }
    @Test void rejectsIneligibleOrFabricatedCitations() throws Exception {
        for (Citation citation : List.of(
                new Citation("boreal-cert-current", "The annual certification reimbursement limit for employees is INR 80000."),
                new Citation("atlas-cert-draft", "Proposed certification reimbursement limit: INR 99000."),
                new Citation("atlas-cert-contractor", "The annual certification reimbursement limit for contractors is INR 10000."),
                new Citation("atlas-cert-historical", "The annual certification reimbursement limit for employees is INR 40000."),
                new Citation("atlas-cert-future", "The annual certification reimbursement limit for employees is INR 35000."),
                new Citation("atlas-cert-current", "INR 999999"))) {
            when(python.answer(any(), any(), anyString())).thenReturn(
                    new AnswerResponse(Outcome.ANSWERED, "Unsupported", List.of(citation)));
            mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01")
                    .contentType("application/json").content(request("2026-09-21")))
                    .andExpect(status().isBadGateway()).andExpect(jsonPath("$.code").value("INVALID_PROVIDER_RESPONSE"));
        }
    }
    @Test void effectiveStartIsInclusiveAndEndExclusive() throws Exception {
        when(python.answer(any(), any(), anyString())).thenReturn(certification());
        mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01").contentType("application/json")
                .content(request("2026-06-01"))).andExpect(status().isOk());
        mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01").contentType("application/json")
                .content(request("2027-01-01"))).andExpect(status().isBadGateway());
    }
    @Test void dependencyFailuresAreNotBusinessOutcomes() throws Exception {
        when(python.answer(any(), any(), anyString())).thenThrow(
                new ApiException(HttpStatus.GATEWAY_TIMEOUT, "PROVIDER_TIMEOUT", "The Python service did not respond in time."));
        mvc.perform(post("/answer").header("X-Caller-Id", "atlas-employee-01").contentType("application/json")
                .content(request("2026-09-21"))).andExpect(status().isGatewayTimeout())
                .andExpect(jsonPath("$.code").value("PROVIDER_TIMEOUT"));
        verify(python, times(1)).answer(any(), any(), anyString());
    }
    @Test void batchPreservesManifestOrderDuplicatesAndEmptyFailures() throws Exception {
        when(python.analyze(any(), any(), anyString(), anyString(), anyString(), any())).thenReturn(analysis());
        var meta = metadata("""
                {"batch_id":"demo","as_of":"2026-09-21","documents":[
                {"document_id":"one","filename":"one.txt"},
                {"document_id":"two","filename":"two.txt"},
                {"document_id":"empty","filename":"empty.txt"}]}
                """);
        mvc.perform(multipart("/batches").file(meta).file(file("two.txt", "same"))
                .file(file("empty.txt", "")).file(file("one.txt", "same"))
                .header("X-Caller-Id", "atlas-employee-01"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.summary.total").value(3))
                .andExpect(jsonPath("$.summary.completed").value(2)).andExpect(jsonPath("$.summary.failed").value(1))
                .andExpect(jsonPath("$.results[0].document_id").value("one"))
                .andExpect(jsonPath("$.results[1].duplicate_of").value("one"))
                .andExpect(jsonPath("$.results[2].error.code").value("EMPTY_FILE"))
                .andExpect(jsonPath("$.results[0].review_required").value(true))
                .andExpect(jsonPath("$.results[2].review_required").value(true));
        verify(python, times(2)).analyze(any(), any(), anyString(), anyString(), anyString(), any());
    }
    @Test void oneProviderFailureDoesNotStopTheBatch() throws Exception {
        when(python.analyze(any(), any(), anyString(), eq("bad"), anyString(), any()))
                .thenThrow(ApiException.malformed());
        when(python.analyze(any(), any(), anyString(), eq("good"), anyString(), any())).thenReturn(analysis());
        mvc.perform(multipart("/batches").file(metadata("""
                {"batch_id":"demo","as_of":"2026-09-21","documents":[
                {"document_id":"bad","filename":"bad.txt"},{"document_id":"good","filename":"good.pdf"}]}
                """)).file(file("bad.txt", "bad")).file(file("good.pdf", "%PDF"))
                .header("X-Caller-Id", "atlas-employee-01"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.results[0].processing_status").value("FAILED"))
                .andExpect(jsonPath("$.results[1].processing_status").value("COMPLETED"));
    }
    @Test void ambiguousFieldsRemainCompletedAndNull() throws Exception {
        when(python.analyze(any(), any(), anyString(), anyString(), anyString(), any())).thenReturn(
                new DocumentAnalysis(new Extracted("certification", null, "INR", null),
                        Map.of("benefit", List.of("Certification reimbursement"), "currency", List.of("INR 22000")),
                        certification(), List.of("Amounts INR 22000 and INR 28000 disagree.", "Reference is missing.")));
        mvc.perform(multipart("/batches").file(metadata("""
                {"batch_id":"demo","as_of":"2026-09-21","documents":[{"document_id":"one","filename":"one.txt"}]}
                """)).file(file("one.txt", "ambiguous")).header("X-Caller-Id", "atlas-employee-01"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.results[0].processing_status").value("COMPLETED"))
                .andExpect(jsonPath("$.results[0].extracted.amount").isEmpty());
    }
    @Test void invalidManifestAndMissingExtraOrRepeatedFilesRejectEntireBatch() throws Exception {
        String valid = """
                {"batch_id":"demo","as_of":"2026-09-21","documents":[{"document_id":"one","filename":"one.txt"}]}
                """;
        mvc.perform(multipart("/batches").file(metadata(valid)).file(file("extra.txt", "x"))
                .header("X-Caller-Id", "atlas-employee-01")).andExpect(status().isBadRequest());
        mvc.perform(multipart("/batches").file(metadata(valid)).file(metadata(valid)).file(file("one.txt", "x"))
                .header("X-Caller-Id", "atlas-employee-01")).andExpect(status().isBadRequest());
        mvc.perform(multipart("/batches").file(metadata(valid)).file(file("one.txt", "x"))
                .file(new MockMultipartFile("extra", "extra.txt", "text/plain", new byte[]{1}))
                .header("X-Caller-Id", "atlas-employee-01")).andExpect(status().isBadRequest());
        mvc.perform(multipart("/batches").file(metadata(valid)).file(file("one.txt", "x"))
                .file(file("one.txt", "x")).header("X-Caller-Id", "atlas-employee-01")).andExpect(status().isBadRequest());
        mvc.perform(multipart("/batches").file(metadata("""
                {"batch_id":"demo","as_of":"2026-09-21","documents":[
                {"document_id":"same","filename":"one.txt"},{"document_id":"same","filename":"two.txt"}]}
                """)).file(file("one.txt", "x")).file(file("two.txt", "y"))
                .header("X-Caller-Id", "atlas-employee-01")).andExpect(status().isBadRequest());
        mvc.perform(multipart("/batches").file(metadata("""
                {"batch_id":"demo","as_of":"2026-09-21","documents":[
                {"document_id":"one","filename":"one.txt"},{"document_id":"two","filename":"two.txt"}]}
                """)).file(file("one.txt", "x")).header("X-Caller-Id", "atlas-employee-01"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(python);
    }
}
