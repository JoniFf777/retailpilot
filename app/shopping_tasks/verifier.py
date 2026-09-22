"""Deterministic business verification before any action preview."""

from __future__ import annotations

from typing import Any

from .contracts import VerificationIssue, VerificationReport, canonical_fingerprint


def verify_task_output(
    kind: str, output: dict[str, Any], *, evidence_available: bool = True
) -> VerificationReport:
    issues: list[VerificationIssue] = []
    if kind == "bundle_selection":
        proposal = output.get("bundle_proposal") or {}
        if proposal.get("outcome") == "needs_information":
            issues.append(
                VerificationIssue(
                    code="missing_bundle_fact",
                    message="组合缺少候选或兼容事实。",
                    missing_facts=list(proposal.get("issues") or []),
                    allowed_repairs=["request_input"],
                )
            )
        elif proposal.get("outcome") == "no_solution":
            issues.append(
                VerificationIssue(
                    code="no_solution_in_checked_candidates",
                    message="当前已检查候选中没有可行组合。",
                    allowed_repairs=["replace_component", "change_budget"],
                )
            )
        elif not proposal.get("options"):
            issues.append(
                VerificationIssue(
                    code="empty_bundle",
                    message="未产生可验证组合。",
                    allowed_repairs=["request_input"],
                )
            )
        constraints = proposal.get("constraints") or {}
        budget = constraints.get("budget")
        currency = constraints.get("currency")
        for option in proposal.get("options") or []:
            option_skus = [
                str(item.get("sku_code")) for item in option.get("items") or []
            ]
            if budget is not None:
                try:
                    if float(option.get("total", "0")) > float(budget):
                        issues.append(
                            VerificationIssue(
                                code="budget_exceeded",
                                message="组合总价超过服务端预算。",
                                affected_skus=option_skus,
                                allowed_repairs=["replace_component", "request_input"],
                            )
                        )
                except (TypeError, ValueError):
                    issues.append(
                        VerificationIssue(
                            code="invalid_total",
                            message="组合总价不是可信 Catalog 数值。",
                            affected_skus=option_skus,
                        )
                    )
            if currency and option.get("currency") != currency:
                issues.append(
                    VerificationIssue(
                        code="currency_mismatch",
                        message="组合币种与目标币种不一致。",
                        affected_skus=option_skus,
                    )
                )
            for fact in option.get("compatibility") or []:
                if fact.get("state") != "supported":
                    issues.append(
                        VerificationIssue(
                            code=f"compatibility_{fact.get('state', 'unknown')}",
                            message=str(fact.get("reason") or "兼容事实未通过。"),
                            affected_skus=[
                                str(fact.get("left")),
                                str(fact.get("right")),
                            ],
                            allowed_repairs=["replace_component", "request_input"],
                        )
                    )
        if not evidence_available:
            issues.append(
                VerificationIssue(
                    code="evidence_unavailable",
                    message="必要证据不可用，不能把组合标为完整通过。",
                    allowed_repairs=["retrieve_evidence"],
                )
            )
    elif kind == "compatibility_diagnosis" and output.get("unresolved"):
        pass
    elif kind == "compatibility_diagnosis" and not output.get("diagnostic_check"):
        issues.append(
            VerificationIssue(
                code="diagnostic_check_missing",
                message="缺少受信安全排查步骤。",
                allowed_repairs=["retrieve_evidence"],
            )
        )
    elif kind == "after_sales_assessment":
        outcome = (output.get("assessment") or {}).get("outcome")
        if outcome in {None, "unknown"}:
            issues.append(
                VerificationIssue(
                    code="after_sales_unknown",
                    message="售后事实或当前政策不足，不能确认资格。",
                    missing_facts=list(
                        (output.get("assessment") or {}).get("missing_facts") or []
                    ),
                )
            )
    status = "pass" if not issues else "repairable"
    if any(
        issue.code in {"after_sales_unknown", "missing_bundle_fact"} for issue in issues
    ):
        status = "needs_input"
    return VerificationReport(
        status=status,
        issues=issues,
        progress_fingerprint=canonical_fingerprint(
            {"kind": kind, "output": output, "issues": [issue.code for issue in issues]}
        ),
    )


__all__ = ["verify_task_output"]
