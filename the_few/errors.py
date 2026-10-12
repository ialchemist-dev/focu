class FewError(Exception):
    def __init__(self, message, code="configuration_error", exit_code=2):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
