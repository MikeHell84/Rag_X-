"""Middleware que exime el chequeo CSRF para las rutas del API (/api/).

Razón: el Dashboard BI (y otros clientes server-to-server) consumen este API
sin manejar cookies de sesión/CSRF. Las rutas públicas del admin (/admin/)
conservan la protección CSRF.
"""

import logging

from django.middleware.csrf import CsrfViewMiddleware

log = logging.getLogger(__name__)


class ApiCsrfExemptMiddleware(CsrfViewMiddleware):
    def process_view(self, request, callback, callback_args, callback_kwargs):
        path = getattr(request, "path", "")
        if path.startswith("/api/"):
            log.info("CSRF exento para %s", path)
            return None
        log.info("CSRF activo para %s", path)
        return super().process_view(request, callback, callback_args, callback_kwargs)
