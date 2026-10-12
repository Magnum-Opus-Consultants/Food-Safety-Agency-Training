"""Learner rules: the entry gate and the moderation guard."""
from decimal import Decimal


def gate_blockers(enrolment) -> list[str]:
    """Rule 1: prerequisite ≥ 50% AND Grade 10 evidence — both, not either. Rule 2: name them."""
    course = enrolment.course
    reasons = []
    if course.entry_gate == "PrerequisiteAndGrade10":
        if enrolment.prerequisite_result is None:
            reasons.append("Prerequisite test result not captured")
        elif enrolment.prerequisite_result < Decimal("50"):
            reasons.append(f"Prerequisite test result is {enrolment.prerequisite_result.normalize():f}% — 50% is required")
        if not enrolment.grade10_evidence_held:
            reasons.append("Grade 10 evidence not filed")
    elif course.entry_gate == "PriorCourse" and course.prior_course_id:
        from learners.models import Moderation

        passed = Moderation.objects.filter(
            outcome="Competent",
            result__enrolment__learner_id=enrolment.learner_id,
            result__enrolment__course_id=course.prior_course_id,
        ).exists()
        if not passed:
            reasons.append(f"No moderated competent result on file for {course.prior_course.title}")
    return reasons


def advance_blockers(enrolment) -> list[str]:
    if enrolment.stage_index >= 4:
        return ["This enrolment is already completed."]
    if enrolment.stage_index == 0:
        return gate_blockers(enrolment)
    return []


def certificate_blockers(result) -> list[str]:
    """Rule 4: a certificate may only be issued after moderation, on a competent outcome."""
    moderation = getattr(result, "moderation", None)
    if moderation is None:
        return ["This result has not been moderated. Every result is moderated by the training manager before a certificate is issued."]
    if moderation.outcome != "Competent":
        return ["The moderated outcome is not yet competent. Record the remediation plan instead."]
    if hasattr(moderation, "certificate"):
        return [f"Certificate {moderation.certificate.reference} has already been issued for this result."]
    return []
