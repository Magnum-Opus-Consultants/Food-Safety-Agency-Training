"""Learner rules: the entry gate and the moderation guard."""
from decimal import Decimal


def gate_blockers(enrolment, requirement=None) -> list[str]:
    """Rule 1: the minimum prerequisites in force for the enrolment's intake — for a test course, the
    pass mark AND Grade 10 evidence, both, not either. Rule 2: name what is outstanding."""
    from courses import requirements

    req = requirement or requirements.for_enrolment(enrolment)
    reasons = []
    if req is None:
        return reasons
    if req.kind == "PrerequisiteAndGrade10":
        mark = req.pass_mark.normalize()
        if enrolment.prerequisite_result is None:
            reasons.append("Prerequisite test result not captured")
        elif enrolment.prerequisite_result < req.pass_mark:
            reasons.append(f"Prerequisite test result is {enrolment.prerequisite_result.normalize():f}% — {mark:f}% is required")
        if not enrolment.grade10_evidence_held:
            reasons.append("Grade 10 evidence not uploaded")
    elif req.kind == "PriorCourse" and req.prior_course_id:
        from learners.models import Moderation

        passed = Moderation.objects.filter(
            outcome="Competent",
            result__enrolment__learner_id=enrolment.learner_id,
            result__enrolment__course_id=req.prior_course_id,
        ).exists()
        if not passed:
            reasons.append(f"No moderated competent result on file for {req.prior_course.title}")
    return reasons


def advance_blockers(enrolment, requirement=None) -> list[str]:
    if enrolment.stage_index >= 3:
        return ["This enrolment is already completed."]
    if enrolment.stage_index == 0:
        return gate_blockers(enrolment, requirement)
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
