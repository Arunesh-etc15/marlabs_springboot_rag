package com.marlabs.policy;

import org.springframework.http.HttpStatus;

public class ApiException extends RuntimeException {
    private final HttpStatus status;
    private final String code;
    public ApiException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }
    public HttpStatus status() { return status; }
    public String code() { return code; }
    public static ApiException invalid(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", message);
    }
    public static ApiException malformed() {
        return new ApiException(HttpStatus.BAD_GATEWAY, "INVALID_PROVIDER_RESPONSE",
                "The Python service returned an invalid response.");
    }
}
