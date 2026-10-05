package com.marlabs.policy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import static com.marlabs.policy.ApiModels.*;
import static org.assertj.core.api.Assertions.*;

class HttpPythonGatewayTest {
    HttpServer server;
    AtomicInteger attempts = new AtomicInteger();
    @AfterEach void stop() { if (server != null) server.stop(0); }
    HttpPythonGateway gateway(String response, int delay, int timeout) throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/answer", exchange -> {
            attempts.incrementAndGet();
            exchange.getRequestBody().readAllBytes();
            try { Thread.sleep(delay); }
            catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
            byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
            try {
                exchange.getResponseHeaders().add("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
            } finally { exchange.close(); }
        });
        server.start();
        ObjectMapper mapper = new ObjectMapper();
        mapper.setPropertyNamingStrategy(com.fasterxml.jackson.databind.PropertyNamingStrategies.SNAKE_CASE);
        return new HttpPythonGateway(mapper, "http://127.0.0.1:" + server.getAddress().getPort(), 500, timeout);
    }
    void call(HttpPythonGateway gateway) {
        gateway.answer(new Caller("Atlas", "employee"), LocalDate.of(2026,9,21), "limit?");
    }
    @Test void malformedOutputFailsWithoutRetry() throws Exception {
        var gateway = gateway("{broken", 0, 1000);
        assertThatThrownBy(() -> call(gateway)).isInstanceOfSatisfying(ApiException.class,
                ex -> assertThat(ex.code()).isEqualTo("INVALID_PROVIDER_RESPONSE"));
        assertThat(attempts.get()).isEqualTo(1);
    }
    @Test void actualReadTimeoutFailsWithoutRetry() throws Exception {
        var gateway = gateway("{}", 300, 50);
        assertThatThrownBy(() -> call(gateway)).isInstanceOfSatisfying(ApiException.class,
                ex -> assertThat(ex.code()).isEqualTo("PROVIDER_TIMEOUT"));
        assertThat(attempts.get()).isEqualTo(1);
    }
    @Test void unavailableServiceFails() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        int port = server.getAddress().getPort();
        server.start();
        server.stop(0);
        server = null;
        var gateway = new HttpPythonGateway(new ObjectMapper(), "http://127.0.0.1:" + port, 100, 100);
        assertThatThrownBy(() -> call(gateway)).isInstanceOfSatisfying(ApiException.class,
                ex -> assertThat(ex.code()).isEqualTo("PROVIDER_UNAVAILABLE"));
    }
}
