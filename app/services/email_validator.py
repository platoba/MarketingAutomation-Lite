"""Email validation service — syntax, disposable domain detection, MX record verification."""

import re
import socket
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# ── Disposable email domains (top 200+) ─────────────────
DISPOSABLE_DOMAINS: set[str] = {
    "10minutemail.com", "guerrillamail.com", "guerrillamailblock.com",
    "mailinator.com", "tempmail.com", "throwaway.email", "fakeinbox.com",
    "sharklasers.com", "guerrillamail.info", "grr.la", "guerrillamail.net",
    "guerrillamail.org", "guerrillamail.de", "yopmail.com", "yopmail.fr",
    "dispostable.com", "trashmail.com", "trashmail.me", "trashmail.net",
    "maildrop.cc", "mailnesia.com", "mailcatch.com", "tempr.email",
    "temp-mail.org", "tempinbox.com", "jetable.org", "getairmail.com",
    "getnada.com", "mohmal.com", "mailsac.com", "harakirimail.com",
    "33mail.com", "mailforspam.com", "safetymail.info", "binkmail.com",
    "spamavert.com", "spamfree24.org", "mytemp.email", "tempail.com",
    "discard.email", "discardmail.com", "discardmail.de", "spamgourmet.com",
    "spam4.me", "trashymail.com", "armyspy.com", "cuvox.de", "dayrep.com",
    "einrot.com", "fleckens.hu", "gustr.com", "jourrapide.com",
    "rhyta.com", "superrito.com", "teleworm.us", "mailnull.com",
    "bugmenot.com", "devnullmail.com", "dodgit.com", "emailondeck.com",
    "inboxalias.com", "mailexpire.com", "mailmoat.com", "mt2015.com",
    "mytrashmail.com", "nobulk.com", "nospamfor.us", "owlpic.com",
    "proxymail.eu", "rmqkr.net", "royal.net", "spambox.us",
    "spamherelots.com", "spaml.com", "uggsrock.com", "wegwerfmail.de",
    "wegwerfmail.net", "zoemail.org", "abyssmail.com", "emvil.com",
    "mailtemp.info", "meltmail.com", "sogetthis.com", "sute.jp",
    "thankyou2010.com", "trashinbox.com", "wh4f.org", "eyepaste.com",
    "fakemailgenerator.com", "drdrb.com", "mailzilla.com", "mintemail.com",
    "oneoffemail.com", "spamfighter.cf", "spamfighter.ga", "spamfighter.gq",
    "spamfighter.ml", "spamfighter.tk", "spamtrail.com", "tempomail.fr",
    "tempsky.com", "throwam.com", "tmail.ws", "tmpmail.net",
    "tmpmail.org", "vzlom4ik.tk", "xjoi.com", "emailfake.com",
    "10minutemail.co.za", "crazymailing.com", "disposable.email",
    "email-fake.com", "emailwarden.com", "fakemail.fr", "generator.email",
    "guerrillamail.biz", "luxusmail.org", "mailtemp.net", "mt2014.com",
    "objectmail.com", "otherinbox.com", "ourklips.com", "pjjkp.com",
    "politikerclub.de", "put2.net", "rcpt.at", "reallymymail.com",
    "recode.me", "regbypass.com", "s0ny.net", "safe-mail.net",
    "sofimail.com", "spamcero.com", "spamoff.de", "tafmail.com",
    "tittbit.in", "tradermail.info", "veryreallyrealmail.com",
    "webemail.me", "weg-werf-email.de", "wegwerfmail.org", "wuzupmail.net",
}

# ── Free email providers (not necessarily disposable) ──
FREE_EMAIL_PROVIDERS: set[str] = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com",
    "aol.com", "icloud.com", "me.com", "mac.com", "protonmail.com",
    "proton.me", "zoho.com", "yandex.com", "mail.com", "gmx.com",
    "gmx.net", "inbox.com", "fastmail.com", "tutanota.com", "qq.com",
    "163.com", "126.com", "yeah.net", "foxmail.com", "sina.com",
    "sohu.com", "aliyun.com",
}

# ── Role-based prefixes (high bounce risk) ─────────────
ROLE_BASED_PREFIXES: set[str] = {
    "admin", "info", "support", "sales", "contact", "help", "office",
    "billing", "webmaster", "postmaster", "hostmaster", "abuse",
    "noreply", "no-reply", "mailer-daemon", "root", "security",
    "marketing", "team", "hello", "feedback", "newsletter", "careers",
    "jobs", "press", "media", "legal", "compliance", "privacy",
    "accounting", "hr", "it", "ops", "operations",
}

# ── Email regex (RFC 5322 simplified) ──────────────────
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)

# ── TLD validation ─────────────────────────────────────
VALID_TLDS: set[str] = {
    "com", "net", "org", "edu", "gov", "mil", "int",
    "io", "co", "ai", "app", "dev", "me", "us", "uk", "de", "fr",
    "jp", "cn", "kr", "au", "ca", "br", "in", "ru", "nl", "se",
    "es", "it", "pl", "ch", "at", "be", "dk", "fi", "no", "pt",
    "cz", "ie", "nz", "za", "sg", "hk", "tw", "th", "my", "ph",
    "id", "vn", "cl", "mx", "ar", "pe", "ec", "co", "ve",
    "info", "biz", "name", "pro", "aero", "coop", "museum",
    "xyz", "online", "site", "store", "shop", "tech", "cloud",
    "space", "live", "blog", "email", "work", "company",
}


class ValidationLevel(str, Enum):
    """Validation strictness level."""
    SYNTAX = "syntax"           # Only check format
    DOMAIN = "domain"           # + disposable/role-based checks
    MX = "mx"                   # + MX record verification
    FULL = "full"               # All checks


class RiskLevel(str, Enum):
    """Email risk classification."""
    LOW = "low"                 # Legitimate business email
    MEDIUM = "medium"           # Free provider but valid
    HIGH = "high"               # Role-based or suspicious
    CRITICAL = "critical"       # Disposable or invalid


@dataclass
class ValidationResult:
    """Result of email validation."""
    email: str
    valid: bool = False
    risk: RiskLevel = RiskLevel.LOW
    score: float = 100.0        # 0-100 quality score
    local_part: str = ""
    domain: str = ""
    tld: str = ""
    is_disposable: bool = False
    is_free_provider: bool = False
    is_role_based: bool = False
    has_mx_records: bool = False
    mx_records: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "valid": self.valid,
            "risk": self.risk.value,
            "score": round(self.score, 1),
            "local_part": self.local_part,
            "domain": self.domain,
            "tld": self.tld,
            "is_disposable": self.is_disposable,
            "is_free_provider": self.is_free_provider,
            "is_role_based": self.is_role_based,
            "has_mx_records": self.has_mx_records,
            "mx_records": self.mx_records,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def validate_syntax(email: str) -> tuple[bool, str, str, str, list[str]]:
    """
    Validate email syntax and extract parts.
    Returns: (valid, local_part, domain, tld, errors)
    """
    errors = []
    email = email.strip().lower()

    if not email:
        return False, "", "", "", ["Email is empty"]

    if len(email) > 320:
        errors.append("Email exceeds 320 character limit")
        return False, "", "", "", errors

    if "@" not in email:
        return False, "", "", "", ["Missing @ symbol"]

    parts = email.rsplit("@", 1)
    if len(parts) != 2:
        return False, "", "", "", ["Invalid email format"]

    local_part, domain = parts

    # Local part checks
    if not local_part:
        errors.append("Empty local part")
    elif len(local_part) > 64:
        errors.append("Local part exceeds 64 characters")
    elif local_part.startswith(".") or local_part.endswith("."):
        errors.append("Local part cannot start or end with a dot")
    elif ".." in local_part:
        errors.append("Local part contains consecutive dots")

    # Domain checks
    if not domain:
        errors.append("Empty domain")
    elif len(domain) > 255:
        errors.append("Domain exceeds 255 characters")
    elif "." not in domain:
        errors.append("Domain must have at least one dot")
    elif domain.startswith("-") or domain.endswith("-"):
        errors.append("Domain labels cannot start or end with hyphen")

    # TLD extraction
    tld = ""
    if "." in domain:
        tld = domain.rsplit(".", 1)[1]

    # Regex check
    if not EMAIL_REGEX.match(email):
        errors.append("Email does not match RFC 5322 format")

    return len(errors) == 0, local_part, domain, tld, errors


def check_disposable(domain: str) -> bool:
    """Check if domain is a known disposable email provider."""
    return domain.lower() in DISPOSABLE_DOMAINS


def check_free_provider(domain: str) -> bool:
    """Check if domain is a free email provider."""
    return domain.lower() in FREE_EMAIL_PROVIDERS


def check_role_based(local_part: str) -> bool:
    """Check if the local part is a role-based address."""
    # Remove dots and plus-addressing for check
    clean = local_part.split("+")[0].replace(".", "")
    return clean.lower() in ROLE_BASED_PREFIXES


def check_mx_records(domain: str, timeout: float = 5.0) -> tuple[bool, list[str]]:
    """
    Check if domain has valid MX records.
    Falls back to A record check if no MX.
    Returns: (has_records, list_of_mx_hosts)
    """
    try:
        import dns.resolver
        try:
            answers = dns.resolver.resolve(domain, "MX", lifetime=timeout)
            mx_hosts = sorted(
                [(r.preference, str(r.exchange).rstrip(".")) for r in answers],
                key=lambda x: x[0],
            )
            return True, [host for _, host in mx_hosts]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            # Try A record as fallback
            try:
                dns.resolver.resolve(domain, "A", lifetime=timeout)
                return True, [domain]
            except Exception:
                return False, []
        except dns.resolver.NoNameservers:
            return False, []
    except ImportError:
        # Fallback to socket-based MX check
        try:
            socket.setdefaulttimeout(timeout)
            mx_host = socket.getfqdn(domain)
            socket.getaddrinfo(domain, 25, socket.AF_INET)
            return True, [mx_host]
        except (socket.gaierror, socket.herror, OSError):
            return False, []


def validate_email(
    email: str,
    level: ValidationLevel = ValidationLevel.DOMAIN,
    check_mx: bool = False,
) -> ValidationResult:
    """
    Comprehensive email validation.

    Args:
        email: Email address to validate
        level: Validation strictness level
        check_mx: Whether to perform MX record lookup (network call)

    Returns:
        ValidationResult with all findings
    """
    result = ValidationResult(email=email.strip().lower())

    # Step 1: Syntax validation
    syntax_valid, local_part, domain, tld, errors = validate_syntax(email)
    result.local_part = local_part
    result.domain = domain
    result.tld = tld
    result.errors.extend(errors)

    if not syntax_valid:
        result.valid = False
        result.risk = RiskLevel.CRITICAL
        result.score = 0
        return result

    if level == ValidationLevel.SYNTAX:
        result.valid = True
        return result

    # Step 2: Domain-level checks
    result.is_disposable = check_disposable(domain)
    result.is_free_provider = check_free_provider(domain)
    result.is_role_based = check_role_based(local_part)

    if result.is_disposable:
        result.errors.append("Disposable email domain detected")
        result.valid = False
        result.risk = RiskLevel.CRITICAL
        result.score = 5
        return result

    # Score deductions
    if result.is_role_based:
        result.warnings.append("Role-based email address (high bounce risk)")
        result.score -= 25
        result.risk = RiskLevel.HIGH

    if result.is_free_provider:
        result.warnings.append("Free email provider")
        result.score -= 10
        if result.risk == RiskLevel.LOW:
            result.risk = RiskLevel.MEDIUM

    # Plus-addressing check
    if "+" in local_part:
        result.warnings.append("Plus-addressing detected (may be a filter alias)")
        result.score -= 5

    # Suspicious patterns
    if re.match(r"^[a-z]{1,2}\d{5,}$", local_part):
        result.warnings.append("Suspicious pattern: short prefix + many digits")
        result.score -= 15
        result.risk = RiskLevel.HIGH

    if len(local_part) > 40:
        result.warnings.append("Unusually long local part")
        result.score -= 5

    if level in (ValidationLevel.DOMAIN, ValidationLevel.SYNTAX):
        result.valid = True
        result.score = max(0, result.score)
        return result

    # Step 3: MX record check
    if level in (ValidationLevel.MX, ValidationLevel.FULL) or check_mx:
        has_mx, mx_hosts = check_mx_records(domain)
        result.has_mx_records = has_mx
        result.mx_records = mx_hosts

        if not has_mx:
            result.errors.append("No MX or A records found for domain")
            result.valid = False
            result.risk = RiskLevel.CRITICAL
            result.score = max(0, result.score - 50)
            return result

    result.valid = True
    result.score = max(0, min(100, result.score))
    return result


def validate_emails_bulk(
    emails: list[str],
    level: ValidationLevel = ValidationLevel.DOMAIN,
) -> dict:
    """
    Validate a batch of emails and return summary statistics.

    Returns:
        {
            "total": int,
            "valid": int,
            "invalid": int,
            "risk_distribution": {"low": N, "medium": N, "high": N, "critical": N},
            "avg_score": float,
            "disposable_count": int,
            "role_based_count": int,
            "results": [ValidationResult.to_dict(), ...]
        }
    """
    results = []
    risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    valid_count = 0
    total_score = 0.0
    disposable_count = 0
    role_based_count = 0

    for email in emails:
        r = validate_email(email, level=level, check_mx=False)
        results.append(r.to_dict())
        risk_dist[r.risk.value] += 1
        total_score += r.score
        if r.valid:
            valid_count += 1
        if r.is_disposable:
            disposable_count += 1
        if r.is_role_based:
            role_based_count += 1

    total = len(emails)
    return {
        "total": total,
        "valid": valid_count,
        "invalid": total - valid_count,
        "risk_distribution": risk_dist,
        "avg_score": round(total_score / max(total, 1), 1),
        "disposable_count": disposable_count,
        "role_based_count": role_based_count,
        "results": results,
    }
