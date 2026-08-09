class RocsaGeneratorError(Exception):
    """Exception de base pour le compilateur ROCSA."""
    pass


class ValidationError(RocsaGeneratorError):
    """Exception levée en cas d'erreur de validation."""
    pass
