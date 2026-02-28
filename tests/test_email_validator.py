"""Tests for email validation service."""

import pytest

from app.services.email_validator import (
    DISPOSABLE_DOMAINS,
    FREE_EMAIL_PROVIDERS,
    ROLE_BASED_PREFIXES,
    RiskLevel,
    ValidationLevel,
    ValidationResult,
    check_disposable,
    check_free_provider,
    check_role_based,
    validate_email,
    validate_emails_bulk,
    validate_syntax,
)


class TestValidateSyntax:
    """Tests for syntax validation."""

    def test_valid_email(self):
        valid, local, domain, tld, errors = validate_syntax("user@example.com")
        assert valid is True
        assert local == "user"
        assert domain == "example.com"
        assert tld == "com"
        assert errors == []

    def test_valid_email_with_dots(self):
        valid, local, domain, tld, errors = validate_syntax("first.last@example.com")
        assert valid is True
        assert local == "first.last"

    def test_valid_email_with_plus(self):
        valid, local, domain, tld, errors = validate_syntax("user+tag@example.com")
        assert valid is True
        assert local == "user+tag"

    def test_valid_email_with_numbers(self):
        valid, *_ = validate_syntax("user123@domain456.co")
        assert valid is True

    def test_valid_email_subdomain(self):
        valid, _, domain, *_ = validate_syntax("user@mail.example.co.uk")
        assert valid is True
        assert domain == "mail.example.co.uk"

    def test_empty_email(self):
        valid, *_, errors = validate_syntax("")
        assert valid is False
        assert "Email is empty" in errors

    def test_no_at_symbol(self):
        valid, *_, errors = validate_syntax("userexample.com")
        assert valid is False
        assert "Missing @ symbol" in errors

    def test_empty_local_part(self):
        valid, *_, errors = validate_syntax("@example.com")
        assert valid is False

    def test_empty_domain(self):
        valid, *_, errors = validate_syntax("user@")
        assert valid is False

    def test_no_dot_in_domain(self):
        valid, *_, errors = validate_syntax("user@localhost")
        assert valid is False
        assert "Domain must have at least one dot" in errors

    def test_consecutive_dots_in_local(self):
        valid, *_, errors = validate_syntax("user..name@example.com")
        assert valid is False
        assert "Local part contains consecutive dots" in errors

    def test_dot_at_start_of_local(self):
        valid, *_, errors = validate_syntax(".user@example.com")
        assert valid is False

    def test_dot_at_end_of_local(self):
        valid, *_, errors = validate_syntax("user.@example.com")
        assert valid is False

    def test_local_part_too_long(self):
        long_local = "a" * 65
        valid, *_, errors = validate_syntax(f"{long_local}@example.com")
        assert valid is False
        assert "Local part exceeds 64 characters" in errors

    def test_email_too_long(self):
        long_email = "a" * 200 + "@" + "b" * 100 + ".com"
        valid, *_, errors = validate_syntax(long_email)
        assert valid is False

    def test_domain_starts_with_hyphen(self):
        valid, *_, errors = validate_syntax("user@-example.com")
        assert valid is False

    def test_case_insensitive(self):
        valid, local, domain, *_ = validate_syntax("User@Example.COM")
        assert valid is True
        assert local == "user"
        assert domain == "example.com"

    def test_whitespace_stripped(self):
        valid, local, *_ = validate_syntax("  user@example.com  ")
        assert valid is True
        assert local == "user"


class TestDomainChecks:
    """Tests for domain-level checks."""

    def test_disposable_mailinator(self):
        assert check_disposable("mailinator.com") is True

    def test_disposable_guerrillamail(self):
        assert check_disposable("guerrillamail.com") is True

    def test_disposable_tempmail(self):
        assert check_disposable("tempmail.com") is True

    def test_disposable_yopmail(self):
        assert check_disposable("yopmail.com") is True

    def test_not_disposable_gmail(self):
        assert check_disposable("gmail.com") is False

    def test_not_disposable_custom(self):
        assert check_disposable("mycompany.com") is False

    def test_free_provider_gmail(self):
        assert check_free_provider("gmail.com") is True

    def test_free_provider_outlook(self):
        assert check_free_provider("outlook.com") is True

    def test_free_provider_qq(self):
        assert check_free_provider("qq.com") is True

    def test_free_provider_protonmail(self):
        assert check_free_provider("protonmail.com") is True

    def test_not_free_provider(self):
        assert check_free_provider("enterprise.co") is False

    def test_role_based_admin(self):
        assert check_role_based("admin") is True

    def test_role_based_info(self):
        assert check_role_based("info") is True

    def test_role_based_support(self):
        assert check_role_based("support") is True

    def test_role_based_noreply(self):
        assert check_role_based("noreply") is True

    def test_role_based_with_plus(self):
        assert check_role_based("admin+test") is True

    def test_role_based_with_dots(self):
        assert check_role_based("a.d.m.i.n") is True

    def test_not_role_based(self):
        assert check_role_based("john") is False

    def test_not_role_based_personal(self):
        assert check_role_based("jane.doe") is False


class TestValidateEmail:
    """Tests for full email validation."""

    def test_valid_business_email(self):
        result = validate_email("ceo@bigcorp.com")
        assert result.valid is True
        assert result.risk == RiskLevel.LOW
        assert result.score > 80

    def test_valid_gmail(self):
        result = validate_email("john@gmail.com")
        assert result.valid is True
        assert result.is_free_provider is True
        assert result.risk == RiskLevel.MEDIUM

    def test_disposable_rejected(self):
        result = validate_email("temp@mailinator.com")
        assert result.valid is False
        assert result.is_disposable is True
        assert result.risk == RiskLevel.CRITICAL

    def test_role_based_warning(self):
        result = validate_email("info@company.com")
        assert result.valid is True
        assert result.is_role_based is True
        assert result.risk == RiskLevel.HIGH
        assert any("Role-based" in w for w in result.warnings)

    def test_invalid_syntax(self):
        result = validate_email("not-an-email")
        assert result.valid is False
        assert result.risk == RiskLevel.CRITICAL
        assert result.score == 0

    def test_syntax_only_level(self):
        result = validate_email("user@mailinator.com", level=ValidationLevel.SYNTAX)
        assert result.valid is True  # Only checks syntax, not disposable

    def test_domain_level(self):
        result = validate_email("user@mailinator.com", level=ValidationLevel.DOMAIN)
        assert result.valid is False  # Catches disposable

    def test_plus_addressing_warning(self):
        result = validate_email("user+test@company.com")
        assert result.valid is True
        assert any("Plus-addressing" in w for w in result.warnings)

    def test_suspicious_pattern(self):
        result = validate_email("a123456@company.com")
        assert result.valid is True
        assert result.risk == RiskLevel.HIGH

    def test_to_dict(self):
        result = validate_email("user@example.com")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "email" in d
        assert "valid" in d
        assert "risk" in d
        assert "score" in d
        assert "warnings" in d
        assert "errors" in d

    def test_empty_email(self):
        result = validate_email("")
        assert result.valid is False

    def test_score_range(self):
        result = validate_email("normal.user@business.io")
        assert 0 <= result.score <= 100

    def test_multiple_warnings_accumulate(self):
        result = validate_email("info+tag@gmail.com")
        assert result.valid is True
        assert len(result.warnings) >= 2  # role-based + plus + free


class TestBulkValidation:
    """Tests for bulk email validation."""

    def test_bulk_mixed(self):
        emails = [
            "valid@company.com",
            "temp@mailinator.com",
            "info@business.com",
            "invalid",
        ]
        result = validate_emails_bulk(emails)
        assert result["total"] == 4
        assert result["valid"] == 2  # valid + info
        assert result["invalid"] == 2  # mailinator + invalid
        assert result["disposable_count"] == 1
        assert result["role_based_count"] == 1
        assert len(result["results"]) == 4

    def test_bulk_empty_list(self):
        result = validate_emails_bulk([])
        assert result["total"] == 0
        assert result["valid"] == 0
        assert result["avg_score"] == 0

    def test_bulk_all_valid(self):
        emails = ["a@company.com", "b@company.com", "c@company.com"]
        result = validate_emails_bulk(emails)
        assert result["valid"] == 3
        assert result["invalid"] == 0

    def test_bulk_all_disposable(self):
        emails = ["a@mailinator.com", "b@guerrillamail.com"]
        result = validate_emails_bulk(emails)
        assert result["valid"] == 0
        assert result["disposable_count"] == 2

    def test_bulk_risk_distribution(self):
        emails = [
            "user@business.com",       # low
            "user@gmail.com",          # medium
            "admin@company.com",       # high (role-based)
            "temp@mailinator.com",     # critical
        ]
        result = validate_emails_bulk(emails)
        dist = result["risk_distribution"]
        assert dist["low"] >= 1
        assert dist["critical"] >= 1

    def test_bulk_avg_score(self):
        emails = ["user@business.com"]
        result = validate_emails_bulk(emails)
        assert result["avg_score"] > 0


class TestDisposableDomains:
    """Verify the disposable domain list is comprehensive."""

    def test_list_has_minimum_entries(self):
        assert len(DISPOSABLE_DOMAINS) >= 100

    def test_common_disposables_included(self):
        common = ["mailinator.com", "guerrillamail.com", "yopmail.com", "tempmail.com"]
        for domain in common:
            assert domain in DISPOSABLE_DOMAINS, f"{domain} missing"

    def test_free_providers_not_in_disposable(self):
        overlap = DISPOSABLE_DOMAINS & FREE_EMAIL_PROVIDERS
        assert len(overlap) == 0, f"Overlap: {overlap}"


class TestRoleBasedPrefixes:
    """Verify role-based prefix list."""

    def test_list_has_minimum_entries(self):
        assert len(ROLE_BASED_PREFIXES) >= 20

    def test_common_roles_included(self):
        common = ["admin", "info", "support", "sales", "noreply", "webmaster"]
        for prefix in common:
            assert prefix in ROLE_BASED_PREFIXES
