"""Tests for the backend API. Run from the project root with:  pytest"""

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app
from backend.schemas.models import ModuleError
from backend.schemas.scan import Gap, Impact, ScanRequest

client = TestClient(app)


def test_root_returns_message():
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_health_check_is_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_scan_zero_pages_returns_failed(monkeypatch):
    """Scanner returns no pages -> failed, health_score None,
    warning explains no checkout page data was collected."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": []}

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["store_url"] == "https://example.com"
    assert body["status"] == "failed"
    assert body["health_score"] is None
    assert body["issues"] == []
    assert len(body["warnings"]) == 1
    assert "checkout page data" in body["warnings"][0].lower()
    assert "scan_id" in body and body["scan_id"]


def test_scan_store_returns_none(monkeypatch):
    """Scanner returns None -> failed, safe message, no exception details."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return None

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["health_score"] is None
    assert body["issues"] == []
    assert "malformed output" in body["warnings"][0].lower()


def test_scan_store_returns_non_dict(monkeypatch):
    """Scanner returns a string -> failed, safe message."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return "not a dictionary"

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["health_score"] is None
    assert body["issues"] == []
    assert "malformed output" in body["warnings"][0].lower()


def test_scan_store_malformed_pages(monkeypatch):
    """Scanner returns pages that is not a list -> failed, safe message."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": "not-a-list"}

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["health_score"] is None
    assert body["issues"] == []
    assert "checkout page data" in body["warnings"][0].lower()


def test_scan_uses_detailed_analysis(monkeypatch):
    """analyze_checkout_detailed is used; issues and warnings read explicitly."""

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": [{"step": "cart", "viewport": "desktop", "success": True}]}

    def fake_analyze_checkout_detailed(scan_data):
        return {
            "issues": [
                {
                    "issue_id": "sdk_outdated",
                    "title": "PayPal JavaScript SDK v5 is outdated",
                    "category": "sdk",
                    "severity": "high",
                    "source": "rule",
                    "evidence": "Store loads SDK v5.",
                    "screenshot_path": "",
                    "fixable_by_agent": True,
                    "confidence": 1.0,
                }
            ],
            "warnings": ["AI vision was disabled; rule-based issues only."],
        }

    def fake_rank_issues(issues):
        return [
            {
                **i,
                "impact": {
                    "issue_id": i["issue_id"],
                    "score": 100,
                    "rank": 1,
                    "rationale": "r",
                    "assumption": "a",
                    "assumption_source": "s",
                },
            }
            for i in issues
        ]

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr(
        "backend.services.scan_service.analyze_checkout_detailed",
        fake_analyze_checkout_detailed,
    )
    monkeypatch.setattr("backend.services.scan_service.rank_issues", fake_rank_issues)
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["warnings"] == ["AI vision was disabled; rule-based issues only."]
    assert len(body["issues"]) == 1
    gap = body["issues"][0]
    assert gap["issue_id"] == "sdk_outdated"
    assert gap["evidence"] == "Store loads SDK v5."
    assert gap["impact"]["assumption_source"] == "s"


def test_description_and_evidence_mapped_separately(monkeypatch):
    """description and evidence are separate fields; evidence not copied to description."""

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": [{"step": "cart", "viewport": "desktop", "success": True}]}

    def fake_analyze_checkout_detailed(scan_data):
        return {
            "issues": [
                {
                    "issue_id": "no_paypal_on_cart",
                    "title": "No PayPal on cart",
                    "category": "presentment",
                    "severity": "high",
                    "source": "rule",
                    "evidence": "No PayPal element on cart page.",
                    "description": "Missing cart presentment.",
                    "screenshot_path": "",
                    "fixable_by_agent": True,
                    "confidence": 1.0,
                }
            ],
            "warnings": [],
        }

    def fake_rank_issues(issues):
        return [
            {
                **i,
                "impact": {
                    "issue_id": i["issue_id"],
                    "score": 90,
                    "rank": 1,
                    "rationale": "r",
                    "assumption": "a",
                    "assumption_source": "s",
                },
            }
            for i in issues
        ]

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr(
        "backend.services.scan_service.analyze_checkout_detailed",
        fake_analyze_checkout_detailed,
    )
    monkeypatch.setattr("backend.services.scan_service.rank_issues", fake_rank_issues)
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    body = response.json()
    gap = body["issues"][0]
    assert gap["issue_id"] == "no_paypal_on_cart"
    assert gap["title"] == "No PayPal on cart"
    assert gap["source"] == "rule"
    assert gap["evidence"] == "No PayPal element on cart page."


def test_scan_module_error(monkeypatch):
    """ModuleError from ai_engine -> failed, safe message, no stack trace."""

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": [{"step": "cart", "viewport": "desktop"}]}

    def fake_analyze_checkout_detailed(scan_data):
        raise ModuleError("AI_UNAVAILABLE", "No API key configured.")

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr(
        "backend.services.scan_service.analyze_checkout_detailed",
        fake_analyze_checkout_detailed,
    )
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["health_score"] is None
    assert body["issues"] == []
    assert "AI_UNAVAILABLE" in body["message"]


def test_scan_unexpected_exception(monkeypatch):
    """Unexpected exception -> failed, generic message, no secret exposure."""

    def fake_scan_store(url, include_mobile=True):
        raise RuntimeError("something broke")

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["health_score"] is None
    assert body["issues"] == []
    assert "unexpected error" in body["message"].lower()
    assert "Traceback" not in body["message"]


def test_scan_requires_store_url():
    response = client.post("/api/scan", json={})
    assert response.status_code == 422  # validation error


def test_scan_invalid_url_private_ip(monkeypatch):
    """Scanner raises InvalidURLError for private IP -> failed with clear message."""
    from backend.schemas.models import ModuleError
    from scanner.exceptions import InvalidURLError

    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        raise InvalidURLError("Private or reserved hostname not allowed: '10.0.0.1'.")

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)

    response = client.post("/api/scan", json={"store_url": "http://10.0.0.1/"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["health_score"] is None
    assert body["issues"] == []
    assert "Invalid store URL" in body["message"]
    assert "Traceback" not in body["message"]


def test_scan_invalid_url_malformed(monkeypatch):
    """Scanner raises InvalidURLError for malformed URL -> failed with clear message."""
    from scanner.exceptions import InvalidURLError

    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        raise InvalidURLError("Unsupported scheme 'ftp' in 'ftp://files.example.com'.")

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)

    response = client.post("/api/scan", json={"store_url": "ftp://files.example.com/"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["health_score"] is None
    assert body["issues"] == []
    assert "Invalid store URL" in body["message"]
    assert "Traceback" not in body["message"]


def test_get_report_existing(monkeypatch):
    """Retrieve a stored report by scan_id."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": []}

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)

    from backend.services.scan_service import run_scan

    result = run_scan(ScanRequest(store_url="https://example.com", include_mobile=True))
    scan_id = result.scan_id

    response = client.get(f"/api/reports/{scan_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["scan_id"] == scan_id
    assert body["status"] == "failed"


def test_get_report_unknown_returns_404(monkeypatch):
    """Unknown scan_id -> HTTP 404."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    response = client.get("/api/reports/unknown-id-12345")
    assert response.status_code == 404
    body = response.json()
    assert "No report found" in body["detail"]


# ------------------------------------------------------------------
# Schema-level validation tests (no HTTP client needed)
# ------------------------------------------------------------------


def test_confidence_defaults_to_one():
    gap = Gap(issue_id="x", title="t")
    assert gap.confidence == 1.0


def test_confidence_accepts_valid_range():
    for value in (0.0, 0.5, 1.0):
        gap = Gap(issue_id="x", title="t", confidence=value)
        assert gap.confidence == value


def test_confidence_rejects_out_of_range():
    for value in (-0.1, 1.1, 2.0):
        try:
            Gap(issue_id="x", title="t", confidence=value)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"confidence={value} should have raised ValidationError")


# ------------------------------------------------------------------
# Backend API scan/fixed service tests
# ------------------------------------------------------------------


def test_scan_successful_with_fix_data(monkeypatch):
    """scan returns completed with gaps, ready for fix."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return {
            "store_url": url,
            "pages": [
                {"step": "cart", "viewport": "desktop", "success": True, "screenshot_path": "", "paypal_elements": []},
                {"step": "checkout", "viewport": "desktop", "success": True, "screenshot_path": "", "paypal_elements": [{"visible": True}]},
            ],
        }

    def fake_analyze_checkout_detailed(scan_data):
        return {
            "issues": [
                {
                    "issue_id": "sdk_outdated",
                    "title": "PayPal JavaScript SDK v5 is outdated",
                    "category": "sdk",
                    "severity": "high",
                    "source": "rule",
                    "evidence": "Store loads SDK v5.",
                    "screenshot_path": "",
                    "fixable_by_agent": True,
                    "confidence": 1.0,
                }
            ],
            "warnings": [],
        }

    def fake_rank_issues(issues):
        return [
            {
                **i,
                "impact": {
                    "issue_id": i["issue_id"],
                    "score": 100,
                    "rank": 1,
                    "rationale": "r",
                    "assumption": "a",
                    "assumption_source": "s",
                },
            }
            for i in issues
        ]

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr(
        "backend.services.scan_service.analyze_checkout_detailed",
        fake_analyze_checkout_detailed,
    )
    monkeypatch.setattr("backend.services.scan_service.rank_issues", fake_rank_issues)
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    response = client.post("/api/scan", json={"store_url": "https://example.com", "include_mobile": True})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert len(body["issues"]) == 1


# ------------------------------------------------------------------
# FIX service tests
# ------------------------------------------------------------------


def test_fix_successful(monkeypatch):
    """scan_id with valid issues -> CODE_AGENT_NOT_READY because placeholder code agent cannot create patched store."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return {
            "store_url": url,
            "pages": [
                {"step": "cart", "viewport": "desktop", "success": True, "screenshot_path": "", "paypal_elements": []},
                {"step": "checkout", "viewport": "desktop", "success": True, "screenshot_path": "", "paypal_elements": [{"visible": True}]},
            ],
        }

    def fake_analyze_checkout_detailed(scan_data):
        return {
            "issues": [
                {
                    "issue_id": "sdk_outdated",
                    "title": "PayPal JavaScript SDK v5 is outdated",
                    "category": "sdk",
                    "severity": "high",
                    "source": "rule",
                    "evidence": "Store loads SDK v5.",
                    "screenshot_path": "",
                    "fixable_by_agent": True,
                    "confidence": 1.0,
                }
            ],
            "warnings": [],
        }

    def fake_rank_issues(issues):
        return [
            {
                **i,
                "impact": {
                    "issue_id": i["issue_id"],
                    "score": 100,
                    "rank": 1,
                    "rationale": "r",
                    "assumption": "a",
                    "assumption_source": "s",
                },
            }
            for i in issues
        ]

    def fake_create_upgrade_plan(repo_path, gaps):
        return [{"gap_id": "sdk_outdated", "file": "app.py", "change_summary": "Upgrade SDK"}]

    def fake_generate_upgrade(repo_path, plan):
        return {
            "branch": "feature/paypal-upgrade",
            "files_changed": ["app.py"],
            "pull_request_url": "https://github.com/user/repo/pull/1",
        }

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr(
        "backend.services.scan_service.analyze_checkout_detailed",
        fake_analyze_checkout_detailed,
    )
    monkeypatch.setattr("backend.services.scan_service.rank_issues", fake_rank_issues)
    monkeypatch.setattr("backend.services.scan_service._reports", {})
    monkeypatch.setattr("backend.services.fix_service.create_upgrade_plan", fake_create_upgrade_plan)
    monkeypatch.setattr("backend.services.fix_service.generate_upgrade", fake_generate_upgrade)
    monkeypatch.setattr("backend.services.verify_service.register_fix", lambda *a, **k: None)
    monkeypatch.setattr("backend.services.verify_service._fixes", {})

    response = client.post("/api/scan", json={"store_url": "http://localhost:8101", "include_mobile": True})
    assert response.status_code == 200
    scan_result = response.json()
    scan_id = scan_result["scan_id"]

    response = client.post("/api/fix", json={"scan_id": scan_id, "issue_ids": ["sdk_outdated"]})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "proposed" and body["fix_id"].startswith("fix_")

    # No fix should be registered
    from backend.services.verify_service import _fixes
    assert _fixes == {}

    # Scan report fix should remain None
    response = client.get(f"/api/reports/{scan_id}")
    assert response.status_code == 200
    report = response.json()
    assert report["fix"] is None


def test_fix_unknown_scan_id(monkeypatch):
    """Unknown scan_id -> 404."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    response = client.post("/api/fix", json={"scan_id": "nonexistent", "issue_ids": ["sdk_outdated"]})
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["code"] == "FIX_NO_STORE"


def test_fix_empty_issue_ids(monkeypatch):
    """Empty issue_ids -> 400."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": [{"step": "cart", "viewport": "desktop", "success": True}]}

    def fake_analyze_checkout_detailed(scan_data):
        return {
            "issues": [
                {
                    "issue_id": "sdk_outdated",
                    "title": "PayPal JavaScript SDK v5 is outdated",
                    "category": "sdk",
                    "severity": "high",
                    "source": "rule",
                    "evidence": "Store loads SDK v5.",
                    "screenshot_path": "",
                    "fixable_by_agent": True,
                    "confidence": 1.0,
                }
            ],
            "warnings": [],
        }

    def fake_rank_issues(issues):
        return [
            {
                **i,
                "impact": {
                    "issue_id": i["issue_id"],
                    "score": 100,
                    "rank": 1,
                    "rationale": "r",
                    "assumption": "a",
                    "assumption_source": "s",
                },
            }
            for i in issues
        ]

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr(
        "backend.services.scan_service.analyze_checkout_detailed",
        fake_analyze_checkout_detailed,
    )
    monkeypatch.setattr("backend.services.scan_service.rank_issues", fake_rank_issues)
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    scan_id = response.json()["scan_id"]

    response = client.post("/api/fix", json={"scan_id": scan_id, "issue_ids": []})
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["code"] == "NO_ISSUES_SELECTED"


def test_fix_unknown_issue_id(monkeypatch):
    """Unknown issue_id -> 400."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": [{"step": "cart", "viewport": "desktop", "success": True}]}

    def fake_analyze_checkout_detailed(scan_data):
        return {
            "issues": [
                {
                    "issue_id": "sdk_outdated",
                    "title": "PayPal JavaScript SDK v5 is outdated",
                    "category": "sdk",
                    "severity": "high",
                    "source": "rule",
                    "evidence": "Store loads SDK v5.",
                    "screenshot_path": "",
                    "fixable_by_agent": True,
                    "confidence": 1.0,
                }
            ],
            "warnings": [],
        }

    def fake_rank_issues(issues):
        return [
            {
                **i,
                "impact": {
                    "issue_id": i["issue_id"],
                    "score": 100,
                    "rank": 1,
                    "rationale": "r",
                    "assumption": "a",
                    "assumption_source": "s",
                },
            }
            for i in issues
        ]

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr(
        "backend.services.scan_service.analyze_checkout_detailed",
        fake_analyze_checkout_detailed,
    )
    monkeypatch.setattr("backend.services.scan_service.rank_issues", fake_rank_issues)
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    scan_id = response.json()["scan_id"]

    response = client.post("/api/fix", json={"scan_id": scan_id, "issue_ids": ["nonexistent_issue"]})
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["code"] == "INVALID_ISSUE_IDS"


def test_fix_code_agent_placeholder(monkeypatch):
    """Code agent placeholder returns empty -> CODE_AGENT_NOT_READY."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": [{"step": "cart", "viewport": "desktop", "success": True}]}

    def fake_analyze_checkout_detailed(scan_data):
        return {
            "issues": [
                {
                    "issue_id": "sdk_outdated",
                    "title": "PayPal JavaScript SDK v5 is outdated",
                    "category": "sdk",
                    "severity": "high",
                    "source": "rule",
                    "evidence": "Store loads SDK v5.",
                    "screenshot_path": "",
                    "fixable_by_agent": True,
                    "confidence": 1.0,
                }
            ],
            "warnings": [],
        }

    def fake_rank_issues(issues):
        return [
            {
                **i,
                "impact": {
                    "issue_id": i["issue_id"],
                    "score": 100,
                    "rank": 1,
                    "rationale": "r",
                    "assumption": "a",
                    "assumption_source": "s",
                },
            }
            for i in issues
        ]

    def fake_create_upgrade_plan(repo_path, gaps):
        return []  # placeholder returns empty

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr(
        "backend.services.scan_service.analyze_checkout_detailed",
        fake_analyze_checkout_detailed,
    )
    monkeypatch.setattr("backend.services.scan_service.rank_issues", fake_rank_issues)
    monkeypatch.setattr("backend.services.scan_service._reports", {})
    monkeypatch.setattr("backend.services.fix_service.create_upgrade_plan", fake_create_upgrade_plan)

    response = client.post("/api/scan", json={"store_url": "http://localhost:8101"})
    assert response.status_code == 200
    scan_id = response.json()["scan_id"]

    response = client.post("/api/fix", json={"scan_id": scan_id, "issue_ids": ["sdk_outdated"]})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "proposed" and body["fix_id"].startswith("fix_")


def test_fix_stored_in_report(monkeypatch):
    """Fix result stored in scan report."""
    monkeypatch.setattr("backend.services.scan_service._reports", {})

    def fake_scan_store(url, include_mobile=True):
        return {"store_url": url, "pages": [{"step": "cart", "viewport": "desktop", "success": True, "paypal_elements": []}]}

    def fake_analyze_checkout_detailed(scan_data):
        return {
            "issues": [
                {
                    "issue_id": "sdk_outdated",
                    "title": "PayPal JavaScript SDK v5 is outdated",
                    "category": "sdk",
                    "severity": "high",
                    "source": "rule",
                    "evidence": "Store loads SDK v5.",
                    "screenshot_path": "",
                    "fixable_by_agent": True,
                    "confidence": 1.0,
                }
            ],
            "warnings": [],
        }

    def fake_rank_issues(issues):
        return [
            {
                **i,
                "impact": {
                    "issue_id": i["issue_id"],
                    "score": 100,
                    "rank": 1,
                    "rationale": "r",
                    "assumption": "a",
                    "assumption_source": "s",
                },
            }
            for i in issues
        ]

    def fake_create_upgrade_plan(repo_path, gaps):
        return [{"gap_id": "sdk_outdated", "file": "app.py", "change_summary": "Upgrade SDK"}]

    def fake_generate_upgrade(repo_path, plan):
        return {
            "branch": "feature/paypal-upgrade",
            "files_changed": ["app.py"],
            "pull_request_url": "https://github.com/user/repo/pull/1",
        }

    monkeypatch.setattr("backend.services.scan_service.scan_store", fake_scan_store)
    monkeypatch.setattr(
        "backend.services.scan_service.analyze_checkout_detailed",
        fake_analyze_checkout_detailed,
    )
    monkeypatch.setattr("backend.services.scan_service.rank_issues", fake_rank_issues)
    monkeypatch.setattr("backend.services.scan_service._reports", {})
    monkeypatch.setattr("backend.services.fix_service.create_upgrade_plan", fake_create_upgrade_plan)
    monkeypatch.setattr("backend.services.fix_service.generate_upgrade", fake_generate_upgrade)
    monkeypatch.setattr("backend.services.verify_service.register_fix", lambda *a, **k: None)
    monkeypatch.setattr("backend.services.verify_service._fixes", {})

    response = client.post("/api/scan", json={"store_url": "http://localhost:8101", "include_mobile": True})
    scan_id = response.json()["scan_id"]

    response = client.post("/api/fix", json={"scan_id": scan_id, "issue_ids": ["sdk_outdated"]})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "proposed" and body["fix_id"].startswith("fix_")

    # No fix should be registered
    from backend.services.verify_service import _fixes
    assert _fixes == {}

    # Scan report fix should remain None
    response = client.get(f"/api/reports/{scan_id}")
    assert response.status_code == 200
    report = response.json()
    assert report["fix"] is None
