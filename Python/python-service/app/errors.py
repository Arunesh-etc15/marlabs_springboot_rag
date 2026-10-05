"""Safe errors returned to Spring Boot without internal exception details."""


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def invalid_provider():
    return ServiceError("INVALID_PROVIDER_RESPONSE", "Ollama returned invalid or unsupported output.")
