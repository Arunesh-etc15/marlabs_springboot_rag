package com.marlabs.policy;

import jakarta.validation.Valid;
import jakarta.servlet.ServletException;
import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import static com.marlabs.policy.ApiModels.*;

@RestController
public class PolicyController {
    private final CallerRegistry callers;
    private final PythonGateway python;
    private final ResponseValidator responses;
    private final BatchService batches;
    public PolicyController(CallerRegistry callers, PythonGateway python,
                            ResponseValidator responses, BatchService batches) {
        this.callers = callers;
        this.python = python;
        this.responses = responses;
        this.batches = batches;
    }
    @PostMapping(value = "/answer", consumes = MediaType.APPLICATION_JSON_VALUE)
    public AnswerResponse answer(@RequestHeader(value = "X-Caller-Id", required = false) String callerId,
                                 @Valid @RequestBody AnswerRequest request) {
        Caller caller = callers.resolve(callerId);
        LocalDate date = date(request.asOf());
        AnswerResponse response = python.answer(caller, date, request.question());
        responses.answer(response, caller, date);
        return response;
    }
    @PostMapping(value = "/batches", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public BatchResponse batch(@RequestHeader(value = "X-Caller-Id", required = false) String callerId,
                               @Valid @RequestPart("metadata") BatchMetadata metadata,
                               @RequestPart("files") List<MultipartFile> files,
                               MultipartHttpServletRequest multipart) throws ServletException, IOException {
        Caller caller = callers.resolve(callerId);
        var parts = multipart.getParts();
        // Servlet parts include JSON metadata without a filename; mock requests use the file map.
        boolean invalid = parts.isEmpty()
                ? multipart.getMultiFileMap().keySet().stream()
                    .anyMatch(name -> !name.equals("metadata") && !name.equals("files"))
                    || multipart.getFiles("metadata").size() != 1
                : parts.stream().filter(part -> part.getName().equals("metadata")).count() != 1
                    || parts.stream().anyMatch(part -> !part.getName().equals("metadata")
                            && !part.getName().equals("files"));
        if (invalid) {
            throw ApiException.invalid("Use exactly one metadata part and repeated files parts.");
        }
        return batches.process(caller, date(metadata.asOf()), metadata, files);
    }
    static LocalDate date(String value) {
        if (value == null || !value.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}")) {
            throw ApiException.invalid("as_of must be a valid date in YYYY-MM-DD format.");
        }
        try { return LocalDate.parse(value); }
        catch (DateTimeParseException ex) {
            throw ApiException.invalid("as_of must be a valid date in YYYY-MM-DD format.");
        }
    }
}
