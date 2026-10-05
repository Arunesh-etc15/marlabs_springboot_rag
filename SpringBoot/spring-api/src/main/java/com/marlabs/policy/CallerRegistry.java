package com.marlabs.policy;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.Map;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import static com.marlabs.policy.ApiModels.*;

@Component
public class CallerRegistry {
    private final Map<String, Caller> callers;
    public CallerRegistry(ObjectMapper mapper) throws IOException {
        try (var input = new ClassPathResource("callers.json").getInputStream()) {
            callers = Map.copyOf(mapper.readValue(input, new TypeReference<Map<String, Caller>>() {}));
        }
    }
    public Caller resolve(String id) {
        if (id == null || id.isBlank() || !callers.containsKey(id)) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_CALLER",
                    "A known X-Caller-Id header is required.");
        }
        return callers.get(id);
    }
}
