package com.marlabs.policy;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.SocketTimeoutException;
import java.time.LocalDate;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.ResourceAccessException;
import static com.marlabs.policy.ApiModels.*;

@Component
public class HttpPythonGateway implements PythonGateway {
    private final RestClient client;
    private final ObjectMapper mapper;
    public HttpPythonGateway(ObjectMapper mapper,
            @Value("${python.base-url}") String baseUrl,
            @Value("${python.connect-timeout-ms}") int connectTimeout,
            @Value("${python.read-timeout-ms}") int readTimeout) {
        if (connectTimeout <= 0 || readTimeout <= 0) {
            throw new IllegalArgumentException("Python timeouts must be positive.");
        }
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeout);
        factory.setReadTimeout(readTimeout);
        client = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
        this.mapper = mapper;
    }
    @Override
    public AnswerResponse answer(Caller caller, LocalDate asOf, String question) {
        return post("/internal/answer", MediaType.APPLICATION_JSON,
                Map.of("tenant", caller.tenant(), "role", caller.role(),
                        "as_of", asOf.toString(), "question", question), AnswerResponse.class);
    }
    @Override
    public DocumentAnalysis analyze(Caller caller, LocalDate asOf, String batchId,
                                     String documentId, String filename, byte[] content) {
        var parts = new LinkedMultiValueMap<String, Object>();
        parts.add("tenant", caller.tenant());
        parts.add("role", caller.role());
        parts.add("as_of", asOf.toString());
        parts.add("batch_id", batchId);
        parts.add("document_id", documentId);
        parts.add("file", new ByteArrayResource(content) {
            @Override public String getFilename() { return filename; }
        });
        return post("/internal/documents/analyze", MediaType.MULTIPART_FORM_DATA, parts, DocumentAnalysis.class);
    }
    private <T> T post(String path, MediaType type, Object body, Class<T> responseType) {
        try {
            // One HTTP call per question/item; this client has no retry interceptor.
            String response = client.post().uri(path).contentType(type).body(body).retrieve().body(String.class);
            if (response == null) throw ApiException.malformed();
            return mapper.readValue(response, responseType);
        } catch (ResourceAccessException ex) {
            Throwable cause = ex;
            while (cause != null) {
                if (cause instanceof SocketTimeoutException) {
                    throw new ApiException(HttpStatus.GATEWAY_TIMEOUT, "PROVIDER_TIMEOUT",
                            "The Python service did not respond in time.");
                }
                cause = cause.getCause();
            }
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "PROVIDER_UNAVAILABLE",
                    "The Python service is unavailable.");
        } catch (RestClientException ex) {
            Throwable cause = ex;
            while (cause != null) {
                if (cause instanceof SocketTimeoutException) {
                    throw new ApiException(HttpStatus.GATEWAY_TIMEOUT, "PROVIDER_TIMEOUT",
                            "The Python service did not respond in time.");
                }
                cause = cause.getCause();
            }
            throw new ApiException(HttpStatus.BAD_GATEWAY, "PROVIDER_ERROR",
                    "The Python service could not process the request.");
        } catch (java.io.IOException ex) {
            throw ApiException.malformed();
        }
    }
}
