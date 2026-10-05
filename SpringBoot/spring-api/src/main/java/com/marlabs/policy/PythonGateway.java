package com.marlabs.policy;

import java.time.LocalDate;
import static com.marlabs.policy.ApiModels.*;

public interface PythonGateway {
    AnswerResponse answer(Caller caller, LocalDate asOf, String question);
    DocumentAnalysis analyze(Caller caller, LocalDate asOf, String batchId,
                             String documentId, String filename, byte[] content);
}
