"""The bounded cross-provider acceptance loop.

This module owns the rules a prompt must not be trusted with: which provider may
judge, whether its session is fresh, what a read-only judge is allowed to see,
what a verdict means, when Done may open, and where the loop stops. Everything
here is a pure decision. Starting a runtime, writing a row, and appending an
event stay with the broker and the store.

Three invariants shape the design:

- A judge is not a second executor. It receives no write zone and no chat
  transcript, only the requirements, the diff and artifact references, and the
  acceptance receipt the executor already produced.
- The loop is short by construction. One judge round, one revision, one final
  judge round, then the user decides. There is no autonomous debate.
- Silence is never acceptance. Output the panel cannot read becomes
  `unreadable`, which escalates instead of closing the gate.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from orch_panel.context_policy import compose_dispatch_handoff
from orch_panel.coordination.models import ArtifactRef

# The two runtimes the console can dispatch. A judge is the other one.
PROVIDERS: tuple[str, ...] = ("codex", "claude")

# One judge opinion, one revision, one final judge opinion. A third model call
# would be the start of an autonomous debate, so the user decides instead.
MAX_JUDGE_ROUNDS = 2

VERDICT_OUTCOMES = frozenset({"accepted", "changes_requested", "unreadable"})
SEVERITIES: tuple[str, ...] = ("blocker", "major", "minor", "note")

# The judge answers with one fenced block the panel can actually parse. Prose
# alone is not a verdict, because guessing at it is how a review turns into a
# rubber stamp.
VERDICT_FENCE = re.compile(r"```(?:verdict|json)?\s*\n(.*?)```", re.DOTALL)

# A short summary is shared history; a full transcript is not. The visible
# review event is truncated to this, and the structure carries the detail.
SUMMARY_LIMIT = 240


# What an acceptance receipt has to be before a judge is told to trust it.
ACCEPTANCE_RECEIPT_SCHEMA = "acceptance-receipt/v2"
HISTORICAL_RECEIPT_SCHEMA = "acceptance-receipt/v1"
EVIDENCE_SCHEMA = "verification-evidence/v2"
ORCHESTRATION_LEVELS = frozenset(
    {"inner_loop", "slice_acceptance", "integration", "release"}
)
STAGE_MANIFEST_SCHEMA = "orchestration-stage/v1"
RECEIPT_FILENAME = "acceptance-receipt.json"
RECEIPT_ROOT: tuple[str, ...] = (".codex", "stages")


class ReviewPolicyError(RuntimeError):
    """A refused review decision. Nothing was started, resumed, or stored."""


def validate_acceptance_receipt(
    path: str,
    payload: object,
    *,
    stage_manifest: object,
    executor_issue_id: str | None,
    evidence_report: object | None = None,
    evidence_report_bytes: bytes | None = None,
    current_identity_digest: str | None = None,
) -> str:
    """Accept only a real passing receipt, and return the stage it belongs to.

    Containment alone is not enough: any readable repository file satisfies it,
    and a judge handed `README.md` would be told to reuse verification evidence
    that does not exist. The document has to say which stage passed, and it has
    to be sitting where that stage's receipt lives. The adjacent canonical
    stage manifest must also name the executor's Beads issue; otherwise a
    passing receipt from an unrelated task could be borrowed unchanged.
    """
    if not isinstance(payload, dict):
        raise ReviewPolicyError(
            f"an acceptance receipt must be a JSON object declaring "
            f"schema_version {ACCEPTANCE_RECEIPT_SCHEMA}"
        )
    schema = payload.get("schema_version")
    if schema == HISTORICAL_RECEIPT_SCHEMA:
        raise ReviewPolicyError(
            f"the receipt at {path!r} is historical {HISTORICAL_RECEIPT_SCHEMA}; "
            f"a new review requires current {ACCEPTANCE_RECEIPT_SCHEMA} evidence"
        )
    if schema != ACCEPTANCE_RECEIPT_SCHEMA:
        raise ReviewPolicyError(
            f"{path!r} does not declare schema_version {ACCEPTANCE_RECEIPT_SCHEMA} "
            "so it is not an acceptance receipt"
        )
    result = str(payload.get("result") or "").strip()
    if result != "passed":
        raise ReviewPolicyError(
            f"the receipt at {path!r} records result {result or 'nothing'!r}; a judge "
            "may only reuse verification that passed"
        )
    stage_id = str(payload.get("stage_id") or "").strip()
    if not stage_id:
        raise ReviewPolicyError(f"the receipt at {path!r} names no stage_id")
    expected = (*RECEIPT_ROOT, stage_id, RECEIPT_FILENAME)
    if PurePosixPath(path).parts != expected:
        raise ReviewPolicyError(
            f"the receipt claims stage {stage_id!r}, so it must be "
            f"{'/'.join(expected)} rather than {path!r}"
        )
    issue_id = str(executor_issue_id or "").strip()
    if not issue_id:
        raise ReviewPolicyError(
            "the executor has no beads_issue_id, so no acceptance receipt can be "
            "bound to the result under review"
        )
    if not isinstance(stage_manifest, dict):
        raise ReviewPolicyError(
            f"stage {stage_id!r} has no readable {STAGE_MANIFEST_SCHEMA} manifest"
        )
    if stage_manifest.get("schema_version") != STAGE_MANIFEST_SCHEMA:
        raise ReviewPolicyError(
            f"stage {stage_id!r} does not declare schema_version "
            f"{STAGE_MANIFEST_SCHEMA}"
        )
    manifest_stage = str(stage_manifest.get("stage_id") or "").strip()
    if manifest_stage != stage_id:
        raise ReviewPolicyError(
            f"the receipt names stage {stage_id!r}, but its stage manifest names "
            f"{manifest_stage or 'nothing'!r}"
        )
    manifest_goal = str(stage_manifest.get("goal_id") or "").strip()
    if manifest_goal != issue_id:
        raise ReviewPolicyError(
            f"acceptance receipt stage {stage_id!r} belongs to {manifest_goal or 'no goal'!r}, "
            f"not executor task {issue_id!r}"
        )
    _validate_v2_evidence(
        path,
        payload,
        evidence_report=evidence_report,
        evidence_report_bytes=evidence_report_bytes,
        current_identity_digest=current_identity_digest,
    )
    return stage_id


def _validate_v2_evidence(
    path: str,
    receipt: dict[str, object],
    *,
    evidence_report: object,
    evidence_report_bytes: bytes | None,
    current_identity_digest: str | None,
) -> None:
    if not isinstance(evidence_report, dict) or evidence_report_bytes is None:
        raise ReviewPolicyError(
            f"the v2 receipt at {path!r} needs its immutable aggregate report"
        )
    if evidence_report.get("schema_version") != EVIDENCE_SCHEMA:
        raise ReviewPolicyError(f"the aggregate report must declare {EVIDENCE_SCHEMA}")
    if hashlib.sha256(evidence_report_bytes).hexdigest() != receipt.get("report_digest"):
        raise ReviewPolicyError("the aggregate report byte digest does not match the receipt")
    unsigned = dict(evidence_report)
    self_digest = unsigned.pop("self_digest", None)
    actual_self_digest = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    if self_digest != actual_self_digest or receipt.get("report_self_digest") != self_digest:
        raise ReviewPolicyError("the aggregate report self-digest is invalid")
    level = receipt.get("orchestration_level")
    report_identity = evidence_report.get("identity")
    if (
        level not in ORCHESTRATION_LEVELS
        or evidence_report.get("orchestration_level") != level
        or not isinstance(report_identity, dict)
        or report_identity.get("orchestration_level") != level
    ):
        raise ReviewPolicyError(
            "the receipt, aggregate report, and verification identity levels differ"
        )
    identity = str(receipt.get("identity_digest") or "")
    if not identity or evidence_report.get("identity_digest") != identity:
        raise ReviewPolicyError("the receipt and aggregate report identity differ")
    if current_identity_digest != identity:
        raise ReviewPolicyError("the current verification identity differs from the receipt")
    if evidence_report.get("result") != "PASS":
        raise ReviewPolicyError("the aggregate verification report is not PASS")
    required = receipt.get("required_steps")
    if not isinstance(required, list) or not required or evidence_report.get("required_steps") != required:
        raise ReviewPolicyError("the receipt and aggregate report required step sets differ")
    steps = evidence_report.get("steps")
    if not isinstance(steps, list) or [item.get("id") for item in steps if isinstance(item, dict)] != required:
        raise ReviewPolicyError("the aggregate report does not account for every required step")
    if any(not isinstance(item, dict) or item.get("result") != "passed" for item in steps):
        raise ReviewPolicyError("the aggregate report contains a non-passing required step")
    producer = receipt.get("producer")
    if (
        not isinstance(producer, dict)
        or producer.get("name") != "orchestration-setup"
        or producer.get("schema") != EVIDENCE_SCHEMA
        or evidence_report.get("producer") != producer
    ):
        raise ReviewPolicyError("the v2 evidence producer identity is missing or inconsistent")


@dataclass(frozen=True)
class Finding:
    """One reviewer observation, kept separate from the prose that framed it."""

    finding_id: str
    severity: str
    summary: str
    actionable: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.finding_id,
            "severity": self.severity,
            "summary": self.summary,
            "actionable": self.actionable,
        }


@dataclass(frozen=True)
class Verdict:
    """What one judge round concluded, in the shape the store persists."""

    outcome: str
    summary: str
    findings: tuple[Finding, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.outcome == "accepted"

    @property
    def actionable_findings(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.actionable)


@dataclass(frozen=True)
class ReviewRound:
    """One persisted round: which pair judged what, and what came back.

    `decided_by` separates a model verdict from the user's own call after the
    loop ran out of rounds. Both close the gate; only one of them is a review.
    """

    review_id: str
    round: int
    executor_dispatch_id: str
    executor_provider: str
    judge_dispatch_id: str
    judge_provider: str
    judge_session_id: str
    outcome: str
    summary: str
    findings: tuple[Finding, ...] = ()
    revision_returned: bool = False
    decided_by: str = "judge"
    created_at: str = ""

    @property
    def accepted(self) -> bool:
        return self.outcome == "accepted"

    @property
    def actionable_findings(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.actionable)


@dataclass(frozen=True)
class ReviewContext:
    """Everything a read-only judge is given, and nothing else.

    The chat stream is deliberately absent. A judge that reads the discussion
    inherits the executor's framing, which is the opposite of an independent
    opinion.
    """

    requirements: str
    receipt: ArtifactRef | None
    diff_refs: tuple[str, ...] = ()
    artifact_refs: tuple[ArtifactRef, ...] = ()
    findings: tuple[Finding, ...] = ()
    round: int = 1


def judge_provider_for(executor_provider: str) -> str:
    """Return the only provider allowed to judge this executor's work."""
    if executor_provider not in PROVIDERS:
        raise ReviewPolicyError(f"unknown executor provider: {executor_provider!r}")
    return next(item for item in PROVIDERS if item != executor_provider)


def assert_cross_provider(*, executor_provider: str, judge_provider: str) -> None:
    """Refuse a judge that is the executor wearing a different hat."""
    if judge_provider not in PROVIDERS:
        raise ReviewPolicyError(f"unknown judge provider: {judge_provider!r}")
    if executor_provider not in PROVIDERS:
        raise ReviewPolicyError(f"unknown executor provider: {executor_provider!r}")
    if judge_provider == executor_provider:
        raise ReviewPolicyError(
            f"a required judge must use the other provider; {executor_provider!r} "
            "cannot review its own result"
        )


def assert_fresh_session(*, judge_session_id: str, used_session_ids: Iterable[str]) -> None:
    """Refuse a judge session that already carries this task's history."""
    used = {item for item in used_session_ids if item}
    if not judge_session_id:
        raise ReviewPolicyError("a required judge needs a fresh runtime session")
    if judge_session_id in used:
        raise ReviewPolicyError(
            f"session {judge_session_id!r} is not fresh; a required judge must start "
            "a new session rather than resume the executor's or a previous judge's"
        )


def review_prompt(context: ReviewContext) -> str:
    """Compose the read-only judge contract.

    The prompt library has no read-only judge card: `review-fix` is a card that
    fixes what it finds, so adopting it would hand a judge the write access this
    loop exists to withhold. The contract is therefore built here, stays short,
    and restates no kernel or skill policy — the runtime loads those itself.
    """
    if not context.requirements.strip():
        raise ReviewPolicyError("a review needs the requirements it is judging against")
    if context.receipt is None:
        raise ReviewPolicyError(
            "a review needs the executor's existing acceptance receipt; without it "
            "the judge would have to rerun verification it was told to reuse"
        )
    goal = "\n".join(
        [
            "judge whether the executor's result meets the requirements below.",
            "This is a read-only review. You have no write zone: do not edit, "
            "create, delete, commit, or run anything that changes the worktree.",
            "",
            "Requirements:",
            context.requirements.strip(),
            "",
            "Output: end your answer with one fenced block tagged `verdict` "
            'containing JSON: {"outcome": "accepted" | "changes_requested", '
            '"summary": "<one sentence>", "findings": [{"id", "severity", '
            '"summary", "actionable"}]}. Severity is blocker, major, minor, or '
            "note. Anything the panel cannot parse counts as no verdict at all.",
        ]
    )
    references = [
        f"Executor acceptance receipt: {context.receipt.path} @ {context.receipt.digest[:12]}"
    ]
    references += [f"Diff under review: {item}" for item in context.diff_refs]
    references += [
        f"Artifact under review: {item.path} @ {item.digest[:12]}"
        for item in context.artifact_refs
    ]
    references += [
        f"Your round {context.round - 1} finding [{item.severity}] "
        f"{item.finding_id}: {item.summary}"
        for item in context.findings
    ]
    return compose_dispatch_handoff(
        goal=goal,
        write_zone="",
        verification=(
            "reuse an acceptance receipt only when it is v2 and its immutable report "
            "was validated. A v1 receipt is historical context, never reusable. Rerun "
            "a check only when you can name the exact evidence gap it leaves and say "
            "which boundary is missing."
        ),
        stop=(
            "you would have to change a file, rerun an unnamed check, or judge work "
            "outside the diff and artifacts listed below."
        ),
        references=tuple(references),
    )


def _finding_from_payload(payload: object, index: int) -> Finding | None:
    if not isinstance(payload, dict):
        return None
    summary = str(payload.get("summary") or payload.get("text") or "").strip()
    if not summary:
        return None
    severity = str(payload.get("severity") or "major").strip().lower()
    if severity not in SEVERITIES:
        severity = "major"
    actionable = payload.get("actionable")
    return Finding(
        finding_id=str(payload.get("id") or f"F{index}").strip() or f"F{index}",
        severity=severity,
        summary=summary,
        # A judge that omits the flag is raising something it wants fixed.
        actionable=True if actionable is None else bool(actionable),
    )


def parse_verdict(text: str) -> Verdict:
    """Translate one judge answer into structure, or into `unreadable`.

    Unreadable is deliberately not a retry and never an acceptance. It means the
    panel has no verdict, which escalates to the user rather than closing Done
    on prose that happened to sound positive.
    """
    raw = text or ""
    for block in reversed(VERDICT_FENCE.findall(raw)):
        try:
            payload = json.loads(block)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict) or "outcome" not in payload:
            continue
        outcome = str(payload.get("outcome") or "").strip().lower()
        if outcome not in {"accepted", "changes_requested"}:
            break
        findings: list[Finding] = []
        for index, item in enumerate(payload.get("findings") or [], start=1):
            finding = _finding_from_payload(item, index)
            if finding is not None:
                findings.append(finding)
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            summary = (
                "accepted without comment"
                if outcome == "accepted"
                else f"{len(findings)} finding(s) returned"
            )
        return Verdict(outcome=outcome, summary=summary[:SUMMARY_LIMIT], findings=tuple(findings))
    return Verdict(
        outcome="unreadable",
        summary="the judge answered without a readable verdict block",
        findings=(),
    )


def judge_rounds(rounds: Sequence[ReviewRound]) -> tuple[ReviewRound, ...]:
    return tuple(item for item in rounds if item.decided_by == "judge")


def next_action(rounds: Sequence[ReviewRound]) -> str:
    """Name the only next step the loop permits.

    Returns one of `request_review`, `return_findings`, `accept`, `escalate`, or
    `resolved`. Every caller that could start a paid call checks this first, so
    the bound lives in one place instead of in each endpoint.
    """
    ordered = tuple(rounds)
    if any(item.decided_by == "user" for item in ordered):
        return "resolved"
    if not ordered:
        return "request_review"
    last = ordered[-1]
    if last.accepted:
        return "accept"
    if last.outcome == "unreadable":
        # Not a disagreement: the judge produced nothing the panel can act on.
        return "escalate"
    if len(judge_rounds(ordered)) >= MAX_JUDGE_ROUNDS:
        return "escalate"
    if not last.actionable_findings:
        # A refusal with nothing to fix cannot be answered by another revision.
        return "escalate"
    return "request_review" if last.revision_returned else "return_findings"


def done_gate(
    *, review_required: bool, rounds: Sequence[ReviewRound]
) -> tuple[bool, str]:
    """Decide whether Done may open, and say exactly what is missing when not.

    A task whose policy does not require review is untouched by this loop: the
    gate is open and the reason is empty.
    """
    if not review_required:
        return True, ""
    ordered = tuple(rounds)
    if not ordered:
        return False, (
            "this task requires cross-provider review: no judge verdict exists yet"
        )
    last = ordered[-1]
    if last.accepted:
        return True, ""
    if last.decided_by == "user":
        return False, (
            "the user rejected this result after the review loop, so it cannot close"
        )
    if last.outcome == "unreadable":
        return False, (
            "the last judge answer had no readable verdict, so Done is still gated"
        )
    return False, (
        f"the {last.judge_provider} judge requested changes in round {last.round}; "
        "Done needs an accepted verdict or an explicit user decision"
    )


def escalation_question(rounds: Sequence[ReviewRound]) -> str:
    """The one visible question the user answers when the loop runs out."""
    ordered = tuple(rounds)
    last = ordered[-1] if ordered else None
    if last is None:
        return "The review loop has no verdict. Please decide how to proceed."
    if last.outcome == "unreadable":
        return (
            f"The {last.judge_provider} judge answered without a readable verdict in "
            f"round {last.round}. The loop stopped; please decide whether to accept "
            "the executor's result, reject it, or take the task over."
        )
    findings = "; ".join(item.summary for item in last.actionable_findings) or last.summary
    return (
        f"After {len(judge_rounds(ordered))} judge round(s) the providers still "
        f"disagree: {findings}. No further model call will start. Please decide "
        "whether to accept the executor's result, reject it, or take the task over."
    )


def review_event_text(verdict: Verdict, *, judge_provider: str, round_number: int) -> str:
    """One short visible line per round. The structure carries the rest."""
    label = {
        "accepted": "accepted",
        "changes_requested": "requested changes",
        "unreadable": "returned no readable verdict",
    }[verdict.outcome]
    head = f"{judge_provider} judge round {round_number}: {label}."
    if not verdict.findings:
        return f"{head} {verdict.summary}".strip()
    listed = ", ".join(
        f"{item.finding_id} ({item.severity})" for item in verdict.findings[:5]
    )
    more = "" if len(verdict.findings) <= 5 else f" +{len(verdict.findings) - 5} more"
    return f"{head} {verdict.summary} Findings: {listed}{more}."


def findings_return_text(rounds: Sequence[ReviewRound]) -> str:
    """The only new instruction the executor session receives on a revision."""
    ordered = tuple(rounds)
    if not ordered:
        raise ReviewPolicyError("there is no verdict to return")
    last = ordered[-1]
    actionable = last.actionable_findings
    if not actionable:
        raise ReviewPolicyError("the last verdict has no actionable finding to return")
    lines = [
        f"Review findings from the {last.judge_provider} judge (round {last.round}). "
        "Address these in this same session; the task and write zone are unchanged.",
    ]
    lines += [
        f"- [{item.severity}] {item.finding_id}: {item.summary}" for item in actionable
    ]
    lines.append(
        "Stop: a finding would require leaving the write zone or changing the goal."
    )
    return "\n".join(lines)


def findings_to_json(findings: Sequence[Finding]) -> str:
    return json.dumps([item.as_dict() for item in findings], ensure_ascii=False)


def findings_from_json(raw: str) -> tuple[Finding, ...]:
    try:
        payload = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return ()
    if not isinstance(payload, list):
        return ()
    findings: list[Finding] = []
    for index, item in enumerate(payload, start=1):
        finding = _finding_from_payload(item, index)
        if finding is not None:
            findings.append(finding)
    return tuple(findings)
