"""The /api/fsa API. REST + JSON, { data, meta } envelopes, refusals as 409 with blockedBy."""
from django.conf import settings
from django.http import HttpRequest
from ninja import NinjaAPI
from ninja.security import SessionAuth

from core.api_support import Refusal


class StaffSession(SessionAuth):
    """Django session cookie + CSRF. A suspended or lapsed account is refused on every request,
    even if the daily suspension job has not yet run."""

    def authenticate(self, request: HttpRequest, key):
        user = request.user
        if user.is_authenticated and user.is_active and not user.is_suspended:
            return user
        return None


api = NinjaAPI(
    title="FSA Academy Training Hub API",
    version="0.1.0",
    urls_namespace="fsa",
    auth=StaffSession(),
    docs_url="/docs" if settings.DEBUG else None,
)


@api.exception_handler(Refusal)
def refusal(request, exc: Refusal):
    return api.create_response(request, exc.body(), status=exc.status)


from identity.api import router as identity_router  # noqa: E402
from oversight.api import router as oversight_router  # noqa: E402
from demand.api import router as demand_router  # noqa: E402
from courses.api import router as courses_router  # noqa: E402
from delivery.api import router as delivery_router  # noqa: E402
from learners.api import router as learners_router  # noqa: E402
from assurance.api import router as assurance_router  # noqa: E402
from audit.api import router as audit_router  # noqa: E402

api.add_router("", identity_router)
api.add_router("", oversight_router)
api.add_router("", demand_router)
api.add_router("", courses_router)
api.add_router("", delivery_router)
api.add_router("", learners_router)
api.add_router("", assurance_router)
api.add_router("", audit_router)
