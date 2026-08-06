"""Autenticación personalizada para eximir CSRF en API endpoints.

Útil para SPAs que no pueden manejar fácilmente el token CSRF.
"""

from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """SessionAuthentication que omite la verificación CSRF.

    Útil para APIs consumidas por SPAs (React, Vue, etc.) donde
    el manejo del token CSRF es complejo o no deseado.
    """

    def enforce_csrf(self, request):
        # Omitir verificación CSRF
        return