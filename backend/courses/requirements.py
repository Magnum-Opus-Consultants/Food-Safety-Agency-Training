"""Which minimum prerequisites apply, and when they may change.

An intake is judged by the requirement version in force on its start date (an enrolment with no
intake, by its registration date). A new version may not take effect on or before the start of any
intake that already has learners, so nobody's requirement changes after they registered."""

import datetime as dt

from core import clock
from courses.models import CourseRequirement


class Book:
    """Every requirement version, loaded once, for registers that judge many enrolments."""

    def __init__(self):
        self.by_course: dict[int, list[CourseRequirement]] = {}
        for r in CourseRequirement.objects.select_related("prior_course").order_by("effective_from", "version"):
            self.by_course.setdefault(r.course_id, []).append(r)

    def on(self, course_id: int, day: dt.date) -> CourseRequirement | None:
        versions = self.by_course.get(course_id, [])
        in_force = [r for r in versions if r.effective_from <= day]
        return in_force[-1] if in_force else (versions[0] if versions else None)

    def for_block(self, block) -> CourseRequirement | None:
        return self.on(block.course_id, block.start_date)

    def for_enrolment(self, enrolment) -> CourseRequirement | None:
        day = enrolment.plan_block.start_date if enrolment.plan_block_id else clock.local_date(enrolment.created_at)
        return self.on(enrolment.course_id, day)

    def current(self, course_id: int) -> CourseRequirement | None:
        return self.on(course_id, clock.today())

    def scheduled(self, course_id: int) -> list[CourseRequirement]:
        """Versions that take effect after today, latest version per date winning."""
        today = clock.today()
        future = {}
        for r in self.by_course.get(course_id, []):
            if r.effective_from > today:
                future[r.effective_from] = r
        return [future[d] for d in sorted(future)]


def for_enrolment(enrolment) -> CourseRequirement | None:
    return Book().for_enrolment(enrolment)


def for_block(block) -> CourseRequirement | None:
    return Book().for_block(block)


def locked_intakes(course):
    """Intakes of this course that already have learners: their requirement is fixed."""
    from delivery.models import PlanBlock

    return list(PlanBlock.objects.filter(course=course, is_active=True, enrolments__is_active=True)
                .distinct().order_by("start_date"))


def earliest_change(course) -> dt.date:
    """The first date a new requirement may take effect: not in the past, and after the start of
    every intake that already has learners."""
    today = clock.today()
    locked = locked_intakes(course)
    after = max((b.start_date for b in locked), default=None)
    return max(today, after + dt.timedelta(days=1)) if after else today
