package com.marlabs.policy;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.time.LocalDate;
import java.util.List;
import java.util.Set;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;
import static com.marlabs.policy.ApiModels.*;

@Component
public class ResponseValidator {
    public record Policy(String id, String tenant, String role, String approvalState,
                         LocalDate effectiveFrom, LocalDate effectiveTo, String text) {}
    private final List<Policy> policies;
    public ResponseValidator(ObjectMapper mapper) throws IOException {
        try (var input = new ClassPathResource("policies.json").getInputStream()) {
            policies = mapper.readValue(input, new TypeReference<List<Policy>>() {});
        }
    }
    public void answer(AnswerResponse response, Caller caller, LocalDate date) {
        require(response != null && response.status() != null && response.citations() != null);
        for (Citation citation : response.citations()) {
            require(citation != null && citation.chunkId() != null
                    && citation.quote() != null && !citation.quote().isBlank());
            require(policies.stream().anyMatch(p -> p.id().equals(citation.chunkId())
                    && p.tenant().equals(caller.tenant()) && p.role().equals(caller.role())
                    && p.approvalState().equals("Approved")
                    && !date.isBefore(p.effectiveFrom()) && date.isBefore(p.effectiveTo())
                    && p.text().contains(citation.quote())));
        }
        switch (response.status()) {
            case ANSWERED -> require(response.answer() != null && !response.answer().isBlank()
                    && !response.citations().isEmpty());
            case INSUFFICIENT_EVIDENCE -> require(response.answer() == null && response.citations().isEmpty());
            case CONFLICT -> require(response.answer() == null && response.citations().stream()
                    .map(Citation::chunkId).distinct().count() >= 2);
        }
    }
    public void analysis(DocumentAnalysis response, Caller caller, LocalDate date) {
        require(response != null && response.extracted() != null
                && response.fieldEvidence() != null && response.issues() != null);
        require(response.issues().stream().allMatch(v -> v != null && !v.isBlank()));
        require(response.fieldEvidence().keySet().stream()
                .allMatch(Set.of("benefit", "amount", "currency", "reference")::contains));
        response.fieldEvidence().values().forEach(quotes -> require(quotes != null && !quotes.isEmpty()
                && quotes.stream().allMatch(q -> q != null && !q.isBlank())));
        Extracted e = response.extracted();
        require(e.benefit() == null || !e.benefit().isBlank());
        require(e.currency() == null || !e.currency().isBlank());
        require(e.reference() == null || !e.reference().isBlank());
        supported(response, "benefit", e.benefit());
        supported(response, "amount", e.amount());
        supported(response, "currency", e.currency());
        supported(response, "reference", e.reference());
        require((e.benefit() == null) == (response.policy() == null));
        if (response.policy() != null) answer(response.policy(), caller, date);
    }
    private void supported(DocumentAnalysis response, String field, Object value) {
        require(value == null ? !response.fieldEvidence().containsKey(field)
                : response.fieldEvidence().containsKey(field));
    }
    private void require(boolean valid) {
        if (!valid) throw ApiException.malformed();
    }
}
