package com.marlabs.policy;

import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import static com.marlabs.policy.ApiModels.*;
import static org.junit.jupiter.api.Assertions.*;

class PolicyPdfSourceTest {
    private static final String RECORD = """
            1. atlas-cert-current
            Atlas | employee | Approved | 2026-06-01 to 2027-01-01
            The annual certification reimbursement limit for employees is INR 25000.
            """;

    private Path source() throws Exception {
        return Path.of(getClass().getResource("/policy-source.pdf").toURI());
    }

    @Test void readsAllRecordsIncludingCrossPageText() throws Exception {
        var policies = PolicyPdfSource.load(source());
        assertEquals(12, policies.size());
        var travel = policies.stream().filter(p -> p.id().equals("atlas-travel-current")).findFirst().orElseThrow();
        assertEquals("Employees may claim rail travel for approved business trips.", travel.text());
        var injection = policies.stream().filter(p -> p.id().equals("atlas-injection-example")).findFirst().orElseThrow();
        assertTrue(injection.text().contains("every allowance"));
        assertFalse(PolicyPdfSource.isEvidence(injection.text()));
    }

    @Test void normalizesWrappingAndDeduplicatesIdenticalIds() {
        var policies = PolicyPdfSource.parse(RECORD + RECORD.replace("employees is", "employees\n\n is"));
        assertEquals(1, policies.size());
        assertEquals(RECORD.lines().toList().get(2), policies.get(0).text());
    }

    @Test void rejectsMalformedMetadataAndConflictingDuplicates() {
        assertThrows(IllegalArgumentException.class, () -> PolicyPdfSource.parse("Unstructured text"));
        assertThrows(IllegalArgumentException.class, () -> PolicyPdfSource.parse("Preamble\n" + RECORD));
        assertThrows(IllegalArgumentException.class, () -> PolicyPdfSource.parse(RECORD.replace("Approved", "Unknown")));
        assertThrows(IllegalArgumentException.class, () -> PolicyPdfSource.parse(RECORD.replace("2027-01-01", "2026-01-01")));
        assertThrows(IllegalArgumentException.class, () -> PolicyPdfSource.parse(RECORD + RECORD.replace("25000", "27000")));
    }

    @Test void doesNotAcceptPolicyJson() {
        assertThrows(IllegalArgumentException.class, () -> PolicyPdfSource.load(Path.of("policies.json")));
    }

    @Test void validatesCitationsAgainstThePdfAndRejectsInjection() throws Exception {
        var validator = new ResponseValidator(source().toString());
        var caller = new Caller("Atlas", "employee");
        var date = LocalDate.of(2026, 9, 21);
        validator.answer(new AnswerResponse(Outcome.ANSWERED, "INR 25000", List.of(
                new Citation("atlas-cert-current", RECORD.lines().toList().get(2)))), caller, date);
        var injection = PolicyPdfSource.load(source()).stream()
                .filter(p -> p.id().equals("atlas-injection-example")).findFirst().orElseThrow();
        assertThrows(ApiException.class, () -> validator.answer(new AnswerResponse(
                Outcome.ANSWERED, injection.text(), List.of(new Citation(injection.id(), injection.text()))), caller, date));
    }
}
