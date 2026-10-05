package com.marlabs.policy;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import static com.marlabs.policy.ApiModels.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveMultipartTest {
    @LocalServerPort int port;
    @MockitoBean PythonGateway python;
    @Test void jsonMetadataWithoutFilenameWorksOverRealHttp() {
        when(python.analyze(any(), any(), anyString(), anyString(), anyString(), any())).thenReturn(
                new DocumentAnalysis(new Extracted(null, null, null, null), Map.of(), null,
                        List.of("No requested benefit or fields could be identified.")));
        var headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        var parts = new LinkedMultiValueMap<String, Object>();
        parts.add("metadata", new HttpEntity<>("""
                {"batch_id":"live","as_of":"2026-09-21","documents":[{"document_id":"one","filename":"one.txt"}]}
                """, headers));
        parts.add("files", new ByteArrayResource("no fields".getBytes(StandardCharsets.UTF_8)) {
            @Override public String getFilename() { return "one.txt"; }
        });
        JsonNode response = RestClient.create("http://localhost:" + port).post().uri("/batches")
                .header("X-Caller-Id", "atlas-employee-01").contentType(MediaType.MULTIPART_FORM_DATA)
                .body(parts).retrieve().body(JsonNode.class);
        assertThat(response).isNotNull();
        assertThat(response.path("summary").path("completed").asInt()).isEqualTo(1);
        assertThat(response.path("results").get(0).path("review_required").asBoolean()).isTrue();
    }
}
