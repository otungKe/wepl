"""
WEPL Pre-Production Audit Report — PDF Generator
Run: python generate_audit_report.py
Output: WEPL_Audit_Report.pdf
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import (
    HexColor, black, white, red, orange, yellow, green, grey
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib import colors
from datetime import date

# ─── Colour palette ────────────────────────────────────────────────────────────
C_DARK      = HexColor("#0f172a")   # near-black
C_ACCENT    = HexColor("#1d4ed8")   # deep blue
C_CRITICAL  = HexColor("#dc2626")   # red
C_HIGH      = HexColor("#ea580c")   # orange
C_MEDIUM    = HexColor("#ca8a04")   # amber
C_LOW       = HexColor("#16a34a")   # green
C_INFO      = HexColor("#2563eb")   # blue
C_BG_LIGHT  = HexColor("#f8fafc")
C_BG_CODE   = HexColor("#1e293b")
C_BORDER    = HexColor("#e2e8f0")
C_SECTION   = HexColor("#1e40af")   # section header blue
C_TABLE_HDR = HexColor("#1e3a5f")

PAGE_W, PAGE_H = A4

def build_styles():
    base = getSampleStyleSheet()

    styles = {
        "cover_title": ParagraphStyle(
            "cover_title", fontSize=32, leading=40, textColor=white,
            fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=8
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontSize=14, leading=20, textColor=HexColor("#94a3b8"),
            fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", fontSize=10, leading=14, textColor=HexColor("#64748b"),
            fontName="Helvetica", alignment=TA_CENTER
        ),
        "h1": ParagraphStyle(
            "h1", fontSize=18, leading=24, textColor=C_SECTION,
            fontName="Helvetica-Bold", spaceBefore=18, spaceAfter=8,
            borderPad=4
        ),
        "h2": ParagraphStyle(
            "h2", fontSize=14, leading=20, textColor=C_DARK,
            fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6
        ),
        "h3": ParagraphStyle(
            "h3", fontSize=11, leading=16, textColor=C_ACCENT,
            fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4
        ),
        "body": ParagraphStyle(
            "body", fontSize=9.5, leading=15, textColor=C_DARK,
            fontName="Helvetica", spaceAfter=5, alignment=TA_JUSTIFY
        ),
        "body_tight": ParagraphStyle(
            "body_tight", fontSize=9, leading=13, textColor=C_DARK,
            fontName="Helvetica", spaceAfter=3
        ),
        "bullet": ParagraphStyle(
            "bullet", fontSize=9.5, leading=14, textColor=C_DARK,
            fontName="Helvetica", leftIndent=14, firstLineIndent=-10, spaceAfter=3
        ),
        "bullet2": ParagraphStyle(
            "bullet2", fontSize=9, leading=13, textColor=C_DARK,
            fontName="Helvetica", leftIndent=28, firstLineIndent=-10, spaceAfter=2
        ),
        "code": ParagraphStyle(
            "code", fontSize=8.5, leading=12, textColor=HexColor("#e2e8f0"),
            fontName="Courier", backColor=C_BG_CODE, leftIndent=10, rightIndent=10,
            spaceBefore=4, spaceAfter=4, borderPad=6
        ),
        "code_inline": ParagraphStyle(
            "code_inline", fontSize=8.5, leading=12, textColor=C_BG_CODE,
            fontName="Courier", backColor=HexColor("#f1f5f9")
        ),
        "caption": ParagraphStyle(
            "caption", fontSize=8, leading=11, textColor=grey,
            fontName="Helvetica-Oblique", alignment=TA_CENTER, spaceAfter=6
        ),
        "label_critical": ParagraphStyle(
            "label_critical", fontSize=9, leading=12, textColor=C_CRITICAL,
            fontName="Helvetica-Bold"
        ),
        "label_high": ParagraphStyle(
            "label_high", fontSize=9, leading=12, textColor=C_HIGH,
            fontName="Helvetica-Bold"
        ),
        "label_medium": ParagraphStyle(
            "label_medium", fontSize=9, leading=12, textColor=C_MEDIUM,
            fontName="Helvetica-Bold"
        ),
        "label_low": ParagraphStyle(
            "label_low", fontSize=9, leading=12, textColor=C_LOW,
            fontName="Helvetica-Bold"
        ),
        "toc_h1": ParagraphStyle(
            "toc_h1", fontSize=10, leading=16, textColor=C_DARK,
            fontName="Helvetica-Bold", leftIndent=0, spaceAfter=2
        ),
        "toc_h2": ParagraphStyle(
            "toc_h2", fontSize=9, leading=14, textColor=HexColor("#374151"),
            fontName="Helvetica", leftIndent=16, spaceAfter=1
        ),
    }
    return styles

def sev_color(s):
    return {
        "CRITICAL": C_CRITICAL,
        "HIGH": C_HIGH,
        "MEDIUM": C_MEDIUM,
        "LOW": C_LOW,
        "INFO": C_INFO,
    }.get(s, C_INFO)

def sev_badge(s, styles):
    c = sev_color(s)
    return Paragraph(
        f'<font color="{c.hexval()}">[{s}]</font>',
        styles["h3"]
    )

def issue_block(sev, title, location, root_cause, impact, fix, redesign, styles):
    """Render a single issue card."""
    sc = sev_color(sev)
    elems = []

    # Title row
    title_style = ParagraphStyle(
        f"ib_title_{sev}", fontSize=10.5, leading=15,
        textColor=C_DARK, fontName="Helvetica-Bold",
        spaceBefore=2, spaceAfter=0
    )
    badge_style = ParagraphStyle(
        f"ib_badge_{sev}", fontSize=8.5, leading=12,
        textColor=sc, fontName="Helvetica-Bold",
        spaceBefore=2, spaceAfter=0
    )

    tbl_data = [[
        Paragraph(f"[{sev}]", badge_style),
        Paragraph(title, title_style),
    ]]
    tbl = Table(tbl_data, colWidths=[2.2*cm, 14.8*cm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))

    def row(label, content):
        lb = ParagraphStyle("_lb", fontSize=8.5, leading=12,
                            textColor=HexColor("#64748b"), fontName="Helvetica-Bold")
        cb = ParagraphStyle("_cb", fontSize=9, leading=13,
                            textColor=C_DARK, fontName="Helvetica")
        return Table([[Paragraph(label, lb), Paragraph(content, cb)]],
                     colWidths=[3.2*cm, 13.8*cm],
                     style=TableStyle([
                         ("VALIGN", (0,0), (-1,-1), "TOP"),
                         ("LEFTPADDING", (0,0), (-1,-1), 0),
                         ("RIGHTPADDING", (0,0), (-1,-1), 4),
                         ("TOPPADDING", (0,0), (-1,-1), 1),
                         ("BOTTOMPADDING", (0,0), (-1,-1), 1),
                     ]))

    inner = [
        Spacer(1, 4),
        tbl,
        Spacer(1, 3),
        row("Location:", location),
        row("Root Cause:", root_cause),
        row("Impact:", impact),
        row("Fix:", fix),
    ]
    if redesign:
        inner.append(row("Ideal Redesign:", redesign))
    inner.append(Spacer(1, 4))

    card = Table([[inner]], colWidths=[17*cm])
    card.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 1, sc),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("BACKGROUND", (0,0), (-1,-1), HexColor("#fafafa")),
    ]))
    return KeepTogether([card, Spacer(1, 8)])


def score_table(scores, styles):
    data = [["Area", "Score / 10", "Verdict"]]
    for area, score, verdict in scores:
        data.append([area, str(score), verdict])
    t = Table(data, colWidths=[9*cm, 3*cm, 5*cm])
    style = [
        ("BACKGROUND", (0,0), (-1,0), C_TABLE_HDR),
        ("TEXTCOLOR", (0,0), (-1,0), white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("ALIGN", (1,0), (1,-1), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("FONTSIZE", (0,1), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_BG_LIGHT, white]),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]
    for i, (_, score, _) in enumerate(scores, start=1):
        c = C_CRITICAL if score < 4 else (C_HIGH if score < 6 else (C_MEDIUM if score < 8 else C_LOW))
        style.append(("TEXTCOLOR", (1, i), (1, i), c))
        style.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    return t


def hr(styles):
    return HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=8, spaceBefore=4)


def build_report():
    styles = build_styles()
    S = styles
    doc = SimpleDocTemplate(
        "WEPL_Audit_Report.pdf",
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2.2*cm, bottomMargin=2.2*cm,
        title="WEPL Pre-Production Audit Report",
        author="Engineering Review Board",
    )

    story = []

    # ═══════════════════════════════════════════════════════════════════════════
    # COVER PAGE
    # ═══════════════════════════════════════════════════════════════════════════
    def cover_bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_DARK)
        canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, PAGE_H - 3*cm, PAGE_W, 3*cm, fill=1, stroke=0)
        canvas.restoreState()

    cover_data = [
        Spacer(1, 5*cm),
        Paragraph("WEPL", S["cover_title"]),
        Paragraph("Pre-Production Engineering Audit", S["cover_sub"]),
        Spacer(1, 0.4*cm),
        HRFlowable(width="60%", thickness=1, color=HexColor("#334155"),
                   hAlign="CENTER", spaceBefore=4, spaceAfter=4),
        Spacer(1, 0.3*cm),
        Paragraph("Fintech-Social Platform · Community Finance · ROSCA · M-Pesa", S["cover_meta"]),
        Spacer(1, 0.4*cm),
        Paragraph(f"Report Date: {date.today().strftime('%B %d, %Y')}", S["cover_meta"]),
        Paragraph("Classification: CONFIDENTIAL — Engineering Leadership Only", S["cover_meta"]),
        Spacer(1, 3*cm),
    ]

    # Render cover on dark background using a table trick
    cover_inner = []
    for item in cover_data:
        cover_inner.append([item])
    cover_tbl = Table(cover_inner, colWidths=[17*cm])
    cover_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))

    # Cover page wrapper with dark background
    cover_wrapper = Table([[cover_tbl]], colWidths=[17*cm], rowHeights=[24*cm])
    cover_wrapper.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_DARK),
        ("LEFTPADDING", (0,0), (-1,-1), 20),
        ("RIGHTPADDING", (0,0), (-1,-1), 20),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(cover_wrapper)
    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # EXECUTIVE SUMMARY & SCORES
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Executive Summary", S["h1"]))
    story.append(hr(S))
    story.append(Paragraph(
        "This report presents the findings of a comprehensive pre-production audit of the WEPL platform — "
        "a Django-based fintech-social application handling community savings, ROSCA cycles, welfare funds, "
        "emergency advances, and M-Pesa payment flows. The audit was conducted against 15 engineering dimensions "
        "covering security, financial integrity, concurrency, scalability, observability, and code quality.",
        S["body"]
    ))
    story.append(Paragraph(
        "The platform demonstrates strong foundational thinking: a clean state-machine ledger, "
        "idempotency-key design, optimistic row-locking, and domain-event decoupling are all present. "
        "However, several CRITICAL defects make the platform <b>NOT safe for production deployment</b> "
        "as-of this audit. Three issues in particular would result in either complete financial-engine "
        "failure or silent loss of customer payments from day one.",
        S["body"]
    ))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Audit Scores by Area", S["h2"]))
    scores = [
        ("Architecture",            6,  "Sound skeleton, dual-path liability"),
        ("Security",                4,  "PIN throttle missing; webhook unsigned"),
        ("Financial Integrity",     3,  "Ledger divergence; non-idempotent keys"),
        ("API Design",              5,  "IDOR holes; missing pagination"),
        ("Database",                6,  "Good locking; missing indexes; CASCADE risk"),
        ("Django-Specific",         6,  "Clean settings; minor anti-patterns"),
        ("Real-Time / WebSockets",  5,  "Auth gap; no rate limits; thread risk"),
        ("Celery / Async",          3,  "Financial queue dead; retry logic broken"),
        ("Scalability",             5,  "Will hit walls at ~5K users"),
        ("Observability / DevOps",  5,  "Sentry wired; metrics absent"),
        ("Testing",                 2,  "Tests pass wrong scenarios silently"),
        ("Failure Scenarios",       3,  "Silent data loss paths present"),
        ("Code Quality",            6,  "Generally readable; critical bugs hidden"),
        ("Performance",             5,  "N+1 queries; unindexed paths"),
        ("Data Consistency",        5,  "Dual-write divergence possible"),
    ]
    story.append(score_table(scores, S))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        "Overall Readiness Score: <b>4.3 / 10 — NOT PRODUCTION READY</b>",
        ParagraphStyle("overall", fontSize=12, leading=16, textColor=C_CRITICAL,
                       fontName="Helvetica-Bold", spaceAfter=4)
    ))
    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # CRITICAL BLOCKERS
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Critical Blockers — Must Fix Before Launch", S["h1"]))
    story.append(hr(S))
    story.append(Paragraph(
        "The following issues are deployment blockers. Any one of them alone would cause "
        "material financial harm, complete service failure, or irrecoverable data loss in production.",
        S["body"]
    ))
    story.append(Spacer(1, 0.2*cm))

    blockers = [
        ("CB-1", "Financial Celery queue never consumed",
         "docker-compose.yml worker command omits -Q financial",
         "ALL B2C disbursements, standing orders, and reconciliation tasks queue forever — "
         "zero payouts ever execute; group funds accumulate but nobody gets paid"),
        ("CB-2", "B2C retry logic permanently disabled",
         "apps/ledger/tasks.py — _handle_payout_failure() called on first exception, before retry",
         "Any transient M-Pesa network hiccup permanently fails and reverses the payout; "
         "users receive error notifications for temporary API timeouts"),
        ("CB-3", "africastalking missing from requirements.txt",
         "requirements.txt — package not listed",
         "Fresh deployment crashes at startup; phone authentication completely broken"),
        ("CB-4", "STK callback swallows all exceptions",
         "apps/mpesa/views.py STKCallbackView._on_success() bare except",
         "Customer pays via M-Pesa STK Push; money leaves their account; "
         "exception in processing silently discards payment; no credit, no retry"),
        ("CB-5", "Welfare & advance repayment idempotency keys use wall clock",
         "apps/contributions/services.py WelfareService.contribute(), AdvanceService.repay()",
         "Celery task retry or network duplicate creates a second LedgerEntry; "
         "fund balance double-counted; advance marked repaid twice"),
        ("CB-6", "PaymentService.create_payment() never writes to LedgerEntry",
         "apps/payments/services.py — ContributionTransaction created, LedgerEntry omitted",
         "Parallel payment path (manual reconciliation) permanently diverges from ledger; "
         "balance queries return wrong totals; audit trail incomplete"),
        ("CB-7", "ContributionJoinRequest.__str__ AttributeError",
         "apps/contributions/models.py — duplicate __str__ references self.voter, self.amendment_id",
         "Any admin page load, Django shell inspection, or log line that stringifies a "
         "join request raises AttributeError; admin panel broken for contribution onboarding"),
        ("CB-8", "M-Pesa webhooks have no signature or IP validation",
         "apps/mpesa/views.py B2CResultView, STKCallbackView — AllowAny, no validation",
         "Attacker posts fake B2C success callback; platform credits a payout that never happened; "
         "direct financial fraud vector"),
    ]

    for cb_id, title, location, impact in blockers:
        row_data = [
            [Paragraph(cb_id, ParagraphStyle("_cid", fontSize=9, fontName="Helvetica-Bold",
                                              textColor=white)),
             Paragraph(title, ParagraphStyle("_ct", fontSize=9.5, fontName="Helvetica-Bold",
                                              textColor=white))],
            [Paragraph("Location", ParagraphStyle("_cl", fontSize=8, fontName="Helvetica-Bold",
                                                    textColor=HexColor("#fca5a5"))),
             Paragraph(location, ParagraphStyle("_clv", fontSize=8.5, fontName="Courier",
                                                 textColor=HexColor("#fef2f2")))],
            [Paragraph("Impact", ParagraphStyle("_ci", fontSize=8, fontName="Helvetica-Bold",
                                                  textColor=HexColor("#fca5a5"))),
             Paragraph(impact, ParagraphStyle("_civ", fontSize=8.5, fontName="Helvetica",
                                               textColor=HexColor("#fef2f2")))],
        ]
        t = Table(row_data, colWidths=[2.2*cm, 14.8*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), C_CRITICAL),
            ("BACKGROUND", (0,1), (-1,-1), HexColor("#7f1d1d")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("GRID", (0,0), (-1,-1), 0.5, HexColor("#991b1b")),
        ]))
        story.append(KeepTogether([t, Spacer(1, 8)]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — ARCHITECTURE
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("1. Architecture Review", S["h1"]))
    story.append(hr(S))

    story.append(Paragraph("1.1 Overall Structure", S["h2"]))
    story.append(Paragraph(
        "WEPL is a Django monolith with a logical app-per-domain layout: users, communities, "
        "contributions, ledger, payments, mpesa, notifications, conversations, activity. "
        "The separation of the immutable ledger from mutable domain state is architecturally sound. "
        "Domain events decouple the service layer from side-effect delivery. "
        "State machines with optimistic concurrency on financial models are the right pattern.",
        S["body"]
    ))
    story.append(Paragraph("1.2 Dual Code Path Problem", S["h2"]))
    story.append(Paragraph(
        "The most dangerous architectural defect is the existence of two independent paths for "
        "recording a payment: <b>ContributionService.contribute()</b> (the primary, ledger-aware path) "
        "and <b>PaymentService.create_payment()</b> (the manual reconciliation path). The second path "
        "writes a ContributionTransaction but never touches LedgerEntry. Any payment recorded via the "
        "payments app will permanently diverge the mutable balance from the immutable ledger.",
        S["body"]
    ))

    story.append(issue_block(
        "CRITICAL", "Dual payment paths cause permanent ledger divergence",
        "apps/payments/services.py:PaymentService.create_payment() — no LedgerEntry write",
        "PaymentService was added without integrating the ledger writer introduced later. "
        "The ContributionTransaction model predates LedgerEntry and was never migrated away.",
        "All manually-reconciled payments produce wrong balance totals. Audit trail incomplete. "
        "Reconciliation task in apps/contributions/tasks.py will flag these as phantom discrepancies.",
        "Add write_ledger_entry() call inside PaymentService.create_payment() after the "
        "ContributionTransaction.objects.create() call. Use the same idempotency_key pattern "
        "as ContributionService: f'payment-{payment.id}-{paying_user.id}'",
        "Eliminate PaymentService entirely. Route all manual reconciliation through "
        "ContributionService.contribute() with a source='manual' flag.",
        S
    ))

    story.append(Paragraph("1.3 Asgi / Channels Configuration", S["h2"]))
    story.append(Paragraph(
        "config/asgi.py hardcodes DJANGO_SETTINGS_MODULE to production at import time. "
        "Any test runner or staging deployment that relies on environment-variable overrides "
        "will silently use production settings for the ASGI stack only, while Django's WSGI "
        "path picks up the override correctly. This creates a split-config surface that is "
        "almost impossible to debug under load.",
        S["body"]
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — SECURITY
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("2. Security Audit", S["h1"]))
    story.append(hr(S))

    story.append(issue_block(
        "CRITICAL", "M-Pesa webhooks accept requests from any IP with no signature check",
        "apps/mpesa/views.py — B2CResultView, STKCallbackView: permission_classes = [AllowAny], no HMAC",
        "Safaricom provides a security credential for signing B2C payloads. No validation was implemented.",
        "Attacker constructs a valid-looking B2C success payload and POSTs it. Platform credits "
        "a disbursement that Safaricom never made. Direct financial fraud, no detection.",
        "1. Restrict to Safaricom CIDR ranges at nginx/firewall level. "
        "2. Validate the SecurityCredential signature on every B2C callback. "
        "3. Add request logging with IP for all webhook endpoints.",
        "Implement a WebhookSignaturePermission class that validates HMAC-SHA256 of the raw "
        "request body against the Safaricom public key. Reject any request failing validation "
        "with HTTP 401 and log the attempt to Sentry.",
        S
    ))

    story.append(issue_block(
        "HIGH", "PIN login endpoint has no rate-limit throttle applied",
        "apps/users/views.py:PINLoginView — no throttle_classes defined; "
        "config/settings/base.py defines 'pin_login': '5/min' but it is never referenced",
        "The throttle scope is defined in REST_FRAMEWORK settings but no view applies "
        "throttle_classes = [ScopedRateThrottle] with throttle_scope = 'pin_login'.",
        "An attacker can brute-force the PIN at full Django request throughput (~300 req/s). "
        "The Redis lockout after 5 attempts is the only protection — bypassed by distributing "
        "attempts across a 30-minute window at just under the lockout threshold.",
        "Add to PINLoginView:\n  throttle_classes = [ScopedRateThrottle]\n  throttle_scope = 'pin_login'",
        "Replace Redis lockout with a token-bucket algorithm per (phone_number, IP). "
        "Add progressive delays: 1s, 2s, 4s... after each failure. Alert on >10 failures/hour.",
        S
    ))

    story.append(issue_block(
        "HIGH", "JWT token transmitted in WebSocket URL query parameter",
        "apps/conversations/jwt_middleware.py — extracts token from ?token=<jwt>",
        "WebSocket upgrade URLs appear in nginx access logs, browser history, referrer headers, "
        "and CDN logs in plaintext.",
        "Any log aggregation system (ELK, Datadog, Splunk) will capture live JWT tokens. "
        "Token exfiltration from logs grants full session access for up to 60 minutes.",
        "Pass the token in the WebSocket subprotocol header "
        "(Sec-WebSocket-Protocol: access_token, <token>) or send it as the first message "
        "after connection and authenticate before allowing any channel operations.",
        "Implement a short-lived WebSocket ticket: POST /ws/ticket/ returns a 30-second "
        "single-use UUID stored in Redis. WebSocket connects with ?ticket=UUID. "
        "Middleware exchanges ticket for user identity.",
        S
    ))

    story.append(issue_block(
        "HIGH", "WebSocket membership not re-validated on each message",
        "apps/conversations/consumers.py:ConversationConsumer.receive() — no auth check",
        "Membership is validated only at connect(). A user removed from a community "
        "mid-session retains WebSocket access until their connection drops.",
        "Removed members can read and send messages for the duration of their connection. "
        "In a long-lived mobile app this could be hours.",
        "In receive(), call an async DB check: await sync_to_async("
        "CommunityMembership.objects.filter)(community=..., user=self.user, is_active=True).aexists() "
        "and close the connection if False.",
        "Cache membership state in the channel layer group. Emit a 'member_removed' group "
        "message when a user is removed; the consumer closes its own connection on receipt.",
        S
    ))

    story.append(issue_block(
        "MEDIUM", "development.py CORS/ALLOWED_HOSTS wildcards risk staging bleed",
        "config/settings/development.py — ALLOWED_HOSTS=['*'], CORS_ALLOW_ALL_ORIGINS=True",
        "No guard prevents development settings from being used in a CI/staging environment.",
        "If a staging deployment accidentally loads development settings (wrong env var), "
        "all origins can make credentialed cross-origin requests to the API.",
        "Add an explicit assertion: assert not os.environ.get('PRODUCTION') at the top of "
        "development.py. Add CORS_ALLOWED_ORIGIN_REGEXES for localhost patterns only.",
        "Use django-environ's Env.bool() with required=True on DJANGO_DEBUG and raise "
        "ImproperlyConfigured if the environment is ambiguous.",
        S
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — FINANCIAL INTEGRITY
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("3. Financial Integrity Audit", S["h1"]))
    story.append(hr(S))

    story.append(issue_block(
        "CRITICAL", "Welfare and advance repayment idempotency keys include wall-clock timestamp",
        "apps/contributions/services.py — WelfareService.contribute() and AdvanceService.repay()",
        "The idempotency key uses timezone.now().strftime('%Y%m%d%H%M%S'). "
        "If the Celery task retries within the same second, the key is identical and is "
        "correctly deduplicated. But if the retry fires even one second later, a new key is "
        "generated and a second LedgerEntry is created.",
        "Double-counting of welfare contributions and advance repayments. Fund balances inflated. "
        "Members appear to have repaid advances they haven't. Irrecoverable without manual "
        "ledger correction.",
        "Derive idempotency keys from stable, business-meaningful identifiers only:\n"
        "  welfare_contrib: f'welfare-contrib-{fund_id}-{user.id}-{period}'\n"
        "  advance_repay:   f'advance-repay-{advance_id}-{sequence_number}'",
        "Create a PaymentIntent model with a client-generated idempotency UUID. All service "
        "calls accept this UUID. The UUID is the idempotency key. No timestamps anywhere "
        "in financial key derivation.",
        S
    ))

    story.append(issue_block(
        "CRITICAL", "B2C task marks transaction FAILED on first attempt, disabling all retries",
        "apps/ledger/tasks.py:execute_b2c_payout() — _handle_payout_failure() called in except "
        "block before self.retry()",
        "The failure handler transitions FinancialTransaction to FAILED state, which is a "
        "terminal state. The retry logic at the bottom of the function checks if state == FAILED "
        "and returns early. The Celery retry therefore never fires.",
        "Every M-Pesa B2C call that gets a network timeout, rate limit, or 5xx is immediately "
        "reversed. Users receive 'Payment failed' for what would be a successful retry. "
        "Effective M-Pesa reliability drops to single-shot success rate (~85%).",
        "Replace _handle_payout_failure() in the except block with raise self.retry(exc=exc, "
        "countdown=60). Only call _handle_payout_failure() in the on_failure Celery hook, "
        "which fires only after all retries are exhausted.",
        "Add a RETRYING state to FinancialTransaction. Transition to RETRYING on retry, "
        "FAILED only on final failure. Add retry_count and last_error fields for observability.",
        S
    ))

    story.append(issue_block(
        "HIGH", "WelfareFund.balance not rolled back when B2C disbursement fails",
        "apps/mpesa/views.py:_on_b2c_failure() — no balance restoration logic",
        "B2C success callback calls WelfareService._mark_disbursed() which decrements "
        "WelfareFund.balance. But the B2C failure callback has no matching increment.",
        "If M-Pesa sends a failure result for a disbursement, the fund balance stays "
        "decremented despite no actual outflow. Repeat disbursement attempts are "
        "blocked by 'insufficient balance' errors even though the money is still in the fund.",
        "In _on_b2c_failure(), restore the fund balance: "
        "WelfareFund.objects.filter(id=...).update(balance=F('balance') + amount). "
        "Write a REVERSAL LedgerEntry.",
        "Make the entire disbursement lifecycle atomic via a saga pattern: each step "
        "registers a compensating transaction. Failure at any step triggers the compensation chain.",
        S
    ))

    story.append(issue_block(
        "HIGH", "STK callback exception handler silently discards customer payments",
        "apps/mpesa/views.py:STKCallbackView._on_success() — bare except: pass",
        "The bare except clause around the payment processing block catches all exceptions "
        "including DatabaseError, IntegrityError, and any service layer exception.",
        "Customer money leaves their M-Pesa wallet. Exception occurs (e.g. DB connection blip). "
        "Payment is never credited. No retry scheduled. No alert fired. Customer calls support. "
        "Manual reconciliation required for every incident.",
        "Replace bare except with:\n  except Exception as exc:\n      logger.error(...)\n"
        "      sentry_sdk.capture_exception(exc)\n      self.retry(exc=exc)\n"
        "Never swallow exceptions in financial callbacks.",
        "Move STK callback processing to a Celery task. The webhook view does one thing: "
        "claim the callback row with UPDATE WHERE status='PENDING', enqueue the task, return 200. "
        "All financial logic runs in the task with full retry and dead-letter handling.",
        S
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 4 — API DESIGN
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("4. API Design Audit", S["h1"]))
    story.append(hr(S))

    story.append(issue_block(
        "HIGH", "IDOR: Any authenticated user can read any community's contributions",
        "apps/contributions/views.py:CommunityContributionsView.get() — no membership check",
        "The view filters contributions by community_id from the URL. No check verifies "
        "that request.user is a member of that community.",
        "Any logged-in user can enumerate all contribution types, amounts, member balances, "
        "and financial history for any private community by iterating community IDs.",
        "Add at the start of get():\n"
        "  if not CommunityMembership.objects.filter(\n"
        "      community_id=community_id, user=request.user, is_active=True\n"
        "  ).exists():\n"
        "      raise PermissionDenied",
        "Extract a membership_required() decorator or a get_community_or_403() shortcut. "
        "Apply it as a mixin to every view that accepts community_id.",
        S
    ))

    story.append(issue_block(
        "HIGH", "Three endpoints return unbounded querysets with no pagination",
        "apps/communities/views.py:DiscoverCommunitiesView, "
        "apps/contributions/views.py:OpenContributionsView, "
        "apps/contributions/views.py:WelfareActivityView (in-memory sort)",
        "No pagination class applied; Django ORM returns the full table.",
        "At 1,000 communities or 10,000 contribution events, these endpoints return "
        "multi-megabyte JSON responses, exhaust database memory, and time out under load.",
        "Apply CursorPagination or PageNumberPagination to all list endpoints. "
        "Add pagination_class to each ViewSet. Add DB-level ORDER BY before slicing.",
        "Enforce a global default: REST_FRAMEWORK = {'DEFAULT_PAGINATION_CLASS': ..., "
        "'PAGE_SIZE': 20}. Override per-view where needed. Any view without explicit "
        "pagination_class = None should inherit the default.",
        S
    ))

    story.append(issue_block(
        "MEDIUM", "PIN transmitted in X-Pin header — logged by most HTTP middleware",
        "apps/contributions/views.py:ContributeView — pin = request.META.get('HTTP_X_PIN')",
        "Custom request headers appear in Django debug toolbar, DRF browsable API logs, "
        "nginx access logs with verbose header logging, and APM traces.",
        "Raw PIN values visible in log aggregation systems. If logs are breached, "
        "attackers obtain PINs in plaintext.",
        "Move PIN to the request body as a dedicated field. Ensure the field is excluded "
        "from all serializer __repr__ and logging. Mark it sensitive in APM (Sentry, Datadog).",
        "Implement a challenge-response: server issues a nonce, client sends HMAC(PIN, nonce). "
        "Server verifies. PIN never transmitted in plaintext.",
        S
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 5 — DATABASE
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("5. Database Audit", S["h1"]))
    story.append(hr(S))

    story.append(issue_block(
        "HIGH", "CASCADE delete on User propagates to ALL financial data",
        "apps/communities/models.py:Community.created_by FK — on_delete=CASCADE, "
        "apps/contributions/models.py:Contribution.created_by FK — on_delete=CASCADE",
        "Django default on_delete propagation was not overridden for creator foreign keys.",
        "Deleting or deactivating any user who created a community or contribution cascades "
        "deletion to ALL associated financial records: contributions, ledger entries, "
        "disbursements, welfare claims. Irreversible data loss.",
        "Change all creator FKs to on_delete=PROTECT or on_delete=SET_NULL with null=True. "
        "Never allow User deletion; instead implement soft-delete (is_active=False).",
        "Add a pre_delete signal on User that raises PermissionDenied if the user has "
        "any financial records. Enforce soft-delete-only at the model level.",
        S
    ))

    story.append(issue_block(
        "MEDIUM", "Notification model foreign keys are plain IntegerFields — no FK constraints",
        "apps/notifications/models.py — community_id, contribution_id, join_request_id, "
        "conversation_id are IntegerField, not ForeignKey",
        "Likely chosen to avoid cross-app import cycles at model definition time.",
        "Orphaned notification rows when referenced objects are deleted. "
        "No ORM traversal, no Django admin inline editing. "
        "Stale notification pointers cause 404s in the notification detail endpoint.",
        "Use GenericForeignKey (ContentType framework) or define explicit ForeignKey with "
        "on_delete=SET_NULL, null=True, db_constraint=False to avoid circular imports.",
        "Create a NotificationTarget polymorphic model. Each notification references one "
        "target via ContentType. Enables ORM traversal, cascade cleanup, and type safety.",
        S
    ))

    story.append(issue_block(
        "MEDIUM", "Missing database indexes on high-frequency query paths",
        "Multiple models — see detail",
        "Indexes not explicitly defined on frequently-filtered non-PK columns.",
        "At scale, unindexed queries become sequential scans. Specific hot paths:\n"
        "  LedgerEntry(contribution_id, entry_date) — financial history queries\n"
        "  FinancialTransaction(idempotency_key) — unique constraint implies index but verify\n"
        "  Notification(user_id, is_read, created_at) — notification feed\n"
        "  ContributionTransaction(contribution_id, user_id) — balance calculations\n"
        "  StandingOrder(next_run_at, is_active) — scheduled task query",
        "Add db_index=True or explicit Meta.indexes with Index(fields=[...]) on each. "
        "Run EXPLAIN ANALYZE on the five queries above under load to validate.",
        "Instrument slow query logging in PostgreSQL (log_min_duration_statement=100ms). "
        "Review pg_stat_user_indexes weekly for zero-usage indexes.",
        S
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 6 — CELERY / ASYNC
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("6. Celery & Async Task Audit", S["h1"]))
    story.append(hr(S))

    story.append(issue_block(
        "CRITICAL", "Financial Celery queue missing from worker command",
        "docker-compose.yml:celery service command:\n"
        "  celery -A config worker -l info -Q default,notifications,payments --concurrency=4\n"
        "(missing: financial)",
        "The task routes in settings/base.py send apps.ledger.tasks.* and "
        "apps.contributions.tasks.* to the 'financial' queue. The worker never subscribes to it.",
        "ALL B2C payouts, ROSCA payout scheduling, standing order execution, balance "
        "reconciliation, and stale transaction recovery tasks queue indefinitely. "
        "No user ever receives a disbursement. Standing orders never fire. "
        "The Redis queue grows unbounded.",
        "Add financial to the worker command: -Q default,notifications,payments,financial\n"
        "Consider running the financial queue on a dedicated worker with --concurrency=2 "
        "to prevent financial task starvation during notification spikes.",
        "Use separate Celery worker services per queue in docker-compose. "
        "Add a health check that alerts if any queue depth exceeds 100 tasks for >5 minutes.",
        S
    ))

    story.append(issue_block(
        "HIGH", "reconcile_balances task iterates ALL records in Python",
        "apps/contributions/tasks.py:reconcile_balances() — "
        "Contribution.objects.filter(is_active=True) full scan, Python loop",
        "No database-level aggregation; all rows fetched into memory, balanced checked in Python.",
        "At 10,000 active contributions, this task fetches millions of LedgerEntry rows "
        "into the Celery worker process. Memory exhaustion, OOM kill, or task timeout. "
        "The reconciliation that's supposed to catch bugs becomes the bug.",
        "Rewrite as a single SQL aggregation:\n"
        "  SELECT c.id, c.current_amount,\n"
        "    SUM(CASE WHEN le.direction='CREDIT' THEN le.amount ELSE -le.amount END)\n"
        "  FROM contributions JOIN ledger_entries GROUP BY c.id\n"
        "  HAVING c.current_amount != SUM(...)",
        "Run reconciliation as a PostgreSQL stored procedure or a Django RawSQL query. "
        "Paginate using keyset pagination on contribution.id. Process in batches of 500.",
        S
    ))

    story.append(issue_block(
        "MEDIUM", "Notification send_notification task not idempotent",
        "apps/notifications/tasks.py:send_notification — max_retries=3, no idempotency key",
        "Celery retry creates a new Notification row each time. No deduplication check.",
        "A transient DB connection error causes 3 duplicate notifications delivered to the "
        "user for every payment event. Trust erosion; notification spam.",
        "Use Notification.objects.get_or_create(idempotency_key=...) where the key is "
        "derived from the triggering event (e.g. f'payment-{payment_id}-{notification_type}').",
        "Adopt a transactional outbox pattern: write notification intent rows in the same "
        "transaction as the domain event. A separate poller delivers them exactly-once.",
        S
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 7 — REAL-TIME / WEBSOCKET
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("7. Real-Time / WebSocket Audit", S["h1"]))
    story.append(hr(S))

    story.append(issue_block(
        "HIGH", "No message size limit on WebSocket receive()",
        "apps/conversations/consumers.py:ConversationConsumer.receive() — no size check",
        "Django Channels passes the full message body to receive() without built-in size limits.",
        "Any connected user sends a 10 MB message. Consumer allocates 10 MB RAM per worker thread. "
        "With 4 Daphne workers × 100 connections each, a coordinated burst exhausts server RAM.",
        "Add at the top of receive():\n"
        "  if len(text_data) > 4096:  # 4KB limit\n"
        "      await self.send(json.dumps({'error': 'Message too large'}))\n"
        "      return",
        "Configure CHANNEL_LAYERS with a max_length constraint. "
        "Add nginx client_max_body_size for WebSocket upgrade connections.",
        S
    ))

    story.append(issue_block(
        "MEDIUM", "Typing indicator has no rate limiting — Redis saturation vector",
        "apps/conversations/consumers.py:_handle_typing() — unconditional channel_layer.group_send()",
        "Every keystroke event triggers a Redis PUBLISH. No debounce, no per-user throttle.",
        "A malicious client sends 1,000 typing events/second. Redis PUBLISH throughput "
        "saturates, degrading ALL channel layer operations including message delivery. "
        "Denial of service against the real-time system.",
        "Track last_typing_sent per user in the consumer instance. Only publish if "
        "> 2 seconds since last event:\n"
        "  now = time.time()\n"
        "  if now - self._last_typing > 2.0:\n"
        "      self._last_typing = now\n"
        "      await self.channel_layer.group_send(...)",
        "Rate limit at the Channels middleware level. Apply the same ScopedRateThrottle "
        "concept to WebSocket event types using a Redis token bucket per user.",
        S
    ))

    story.append(issue_block(
        "MEDIUM", "Multiple sync_to_async DB calls per message hit Django thread pool",
        "apps/conversations/consumers.py — sync_to_async wrapping ORM calls in receive()",
        "Each sync_to_async call runs in Django's threadpool executor (default: cpu_count × 5). "
        "Under high WebSocket concurrency, all threads are occupied with DB calls.",
        "Thread pool exhaustion blocks all sync_to_async calls across all consumers, "
        "freezing every connected WebSocket client simultaneously.",
        "Migrate ORM calls to async-native Django ORM syntax (Django 4.1+):\n"
        "  message = await Message.objects.acreate(...)\n"
        "  members = [m async for m in community.members.aiterator()]",
        "Adopt full async Django views and consumers. Eliminate sync_to_async entirely "
        "for the hot path. Keep sync_to_async only for third-party libraries without async support.",
        S
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 8 — TESTING
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("8. Testing Audit", S["h1"]))
    story.append(hr(S))

    story.append(Paragraph(
        "The test suite has a structural defect that makes it more dangerous than no tests: "
        "several tests assert on the wrong exception types, meaning they silently PASS even when "
        "the system is completely broken. This creates false confidence.",
        S["body"]
    ))

    story.append(issue_block(
        "CRITICAL", "Tests assert wrong exception types — silently pass on broken code",
        "apps/contributions/tests.py — multiple test cases",
        "Services raise django.core.exceptions.PermissionDenied but tests catch "
        "the built-in PermissionError. These are different classes with no inheritance relationship.",
        "assertRaises(PermissionError) passes vacuously because PermissionDenied is not "
        "a subclass of PermissionError. The permission check could be completely removed "
        "from the service and the test would still pass. "
        "Authorization is effectively untested.",
        "Replace all assertRaises(PermissionError) with "
        "assertRaises(PermissionDenied) (from django.core.exceptions). "
        "Add a linting rule: grep for 'PermissionError' in test files and fail CI.",
        "Write a base TestCase mixin that automatically validates the exception type "
        "matches the service contract. Use mypy strict mode to catch exception type mismatches.",
        S
    ))

    story.append(issue_block(
        "CRITICAL", "Three test methods call non-existent service methods",
        "apps/contributions/tests.py:\n"
        "  WelfareTests.test_get_or_create_fund calls WelfareService.get_or_create_fund() "
        "  (actual: get_or_create_community_fund())\n"
        "  WelfareTests.test_majority_vote_disburses_claim calls WelfareService.vote_on_claim() "
        "  (method does not exist)\n"
        "  EmergencyAdvanceTests.test_admin_can_approve asserts status == 'APPROVED' "
        "  (actual state after approve_advance is DISBURSED)",
        "Tests were written against an earlier API design and never updated after refactoring. "
        "They raise AttributeError immediately and are excluded from the suite by the test runner "
        "as erroring (not failing), masking the coverage gap.",
        "These tests appear to cover critical welfare and emergency flows but actually provide "
        "zero coverage. Production bugs in these flows will not be caught by CI.",
        "Fix immediately:\n"
        "  1. get_or_create_fund → get_or_create_community_fund\n"
        "  2. vote_on_claim → implement the missing method or rewrite the test\n"
        "  3. assert status == 'DISBURSED' (not 'APPROVED')",
        "Add pytest-strict-markers and configure CI to treat any test error as a failure. "
        "Add mypy type checking to service method calls in tests.",
        S
    ))

    story.append(issue_block(
        "HIGH", "No integration tests for M-Pesa callback flows",
        "tests/ directory — no mpesa tests found",
        "M-Pesa integration is complex and failure-prone. No tests cover STK callback "
        "processing, B2C result handling, or reconciliation logic.",
        "Silent financial data loss (CB-4) was never caught because no test exercises "
        "the callback path with a simulated exception.",
        "Write integration tests using responses or httpretty to mock the M-Pesa API. "
        "Test: successful STK callback credits balance; failed callback does not; "
        "duplicate callback is idempotent; malformed payload returns 400.",
        "Set up a Safaricom sandbox environment for staging. Run full E2E payment "
        "flows in CI against the sandbox before every production deploy.",
        S
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 9 — PERFORMANCE & SCALABILITY
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("9. Performance & Scalability", S["h1"]))
    story.append(hr(S))

    story.append(issue_block(
        "HIGH", "N+1 queries in ContributionSerializer",
        "apps/contributions/serializers.py:\n"
        "  get_participant_count() — COUNT(*) per contribution\n"
        "  get_user_balance() — LedgerEntry aggregate per contribution",
        "SerializerMethodField calls fire individual DB queries per object in the list response.",
        "A list of 50 contributions fires 100+ queries. Latency grows linearly. "
        "At 200 contributions visible on the home feed, a single page load issues 400 queries.",
        "Use prefetch_related + annotate:\n"
        "  qs.annotate(participant_count=Count('participants'), "
        "user_balance=Subquery(...))\n"
        "Pass the annotation values into the serializer context.",
        "Define a ContributionSummarySerializer for list views with only denormalized "
        "fields. Use ContributionDetailSerializer only for single-object endpoints.",
        S
    ))

    story.append(issue_block(
        "HIGH", "M-Pesa access token fetched on every API call",
        "apps/mpesa/services.py:MpesaService._get_access_token() — HTTP call every invocation",
        "No caching layer; Daraja access tokens are valid for 3600 seconds.",
        "Each STK Push or B2C initiation makes two HTTP calls to Safaricom: one for the "
        "access token, one for the actual API. Doubles latency per payment, "
        "hits Daraja rate limits under load.",
        "Cache the token in Redis:\n"
        "  token = cache.get('mpesa_access_token')\n"
        "  if not token:\n"
        "      token = self._fetch_access_token()\n"
        "      cache.set('mpesa_access_token', token, timeout=3500)",
        "Wrap _get_access_token() with a thread-safe singleton refresh pattern. "
        "Add a Celery Beat task that pre-fetches the token every 58 minutes.",
        S
    ))

    story.append(issue_block(
        "MEDIUM", "MyCommunitiesView uses 4 LEFT JOINs for activity sorting",
        "apps/communities/views.py:MyCommunitiesView — complex GREATEST annotation query",
        "The view annotates each community with the latest activity timestamp across "
        "4 different related models using GREATEST(). This generates a complex SQL query "
        "with 4 LEFT JOINs and 4 subqueries per community.",
        "For a user in 20 communities, this is a join-heavy query that cannot use "
        "standard indexes. Execution time grows super-linearly with community size and activity volume.",
        "Add a last_activity_at field to Community, updated via a signal or service "
        "method whenever activity occurs. Sorting becomes a simple ORDER BY index scan.",
        "Implement a Redis sorted set per user: community_activity:{user_id} storing "
        "community_id → timestamp scores. Update on write. Read for feed ordering with O(log N).",
        S
    ))

    story.append(Paragraph("Scaling Failure Points", S["h2"]))
    story.append(Paragraph(
        "The following are the predicted load thresholds at which specific subsystems will fail "
        "without architectural changes:",
        S["body"]
    ))

    scale_data = [
        ["User Load", "Subsystem", "Failure Mode", "Primary Cause"],
        ["~500 users", "Notification queue", "Backlog grows unbounded", "Duplicate sends from non-idempotent retries"],
        ["~1,000 users", "DiscoverCommunities endpoint", "Response timeout / OOM", "Full table scan, no pagination"],
        ["~2,000 users", "MyCommunitiesView", "P99 latency > 5s", "4-JOIN annotation query with no covering index"],
        ["~5,000 users", "reconcile_balances task", "OOM kill in Celery worker", "Full Python iteration over all ledger entries"],
        ["~10,000 users", "WebSocket typing indicators", "Redis saturation", "Unbounded PUBLISH rate per connected user"],
        ["~50,000 users", "Celery broker (shared Redis)", "Redis memory exhausted", "Broker and cache on same Redis instance"],
    ]
    scale_tbl = Table(scale_data, colWidths=[2.5*cm, 3.5*cm, 5.5*cm, 5.5*cm])
    scale_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_TABLE_HDR),
        ("TEXTCOLOR", (0,0), (-1,0), white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 8.5),
        ("FONTSIZE", (0,1), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_BG_LIGHT, white]),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(scale_tbl)
    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 10 — OBSERVABILITY
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("10. Observability & DevOps", S["h1"]))
    story.append(hr(S))

    story.append(Paragraph("What's Present (Good)", S["h2"]))
    present = [
        "Sentry SDK integrated for Django and Celery with DSN from environment",
        "recover_stale_processing_transactions() Celery Beat task logs CRITICAL alerts for stuck transactions",
        "Celery task routing to named queues enables queue-level monitoring",
        "CONN_MAX_AGE=60 for persistent DB connections in production",
        "Non-root Docker user (appuser) for container security",
    ]
    for item in present:
        story.append(Paragraph(f"• {item}", S["bullet"]))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("Critical Gaps", S["h2"]))

    gaps = [
        ("HIGH", "No Prometheus / StatsD metrics",
         "No business metrics: payment success rate, OTP delivery rate, "
         "disbursement lag, active WebSocket connections. "
         "Impossible to build SLOs or detect degradation trends without page-level alerts."),
        ("HIGH", "No dead-letter queue for failed Celery tasks",
         "Tasks that exhaust retries are silently dropped. "
         "Failed B2C payouts (after the retry bug is fixed) disappear with no "
         "operator notification. Add a dead-letter queue and PagerDuty alert for any DLQ entry."),
        ("HIGH", "No structured logging",
         "logger.info/error calls use string formatting. "
         "Cannot query logs by payment_id, community_id, or user_id in ELK/Splunk. "
         "Add structlog or python-json-logger with standard fields on every log line."),
        ("MEDIUM", "migrate on every container start is dangerous",
         "docker-compose.yml runs python manage.py migrate as the web service entrypoint. "
         "In a multi-replica deployment, two containers racing to apply the same migration "
         "causes IntegrityError or table-lock timeout. "
         "Run migrations as a one-shot init container, not as the web process entrypoint."),
        ("MEDIUM", "No health check endpoint",
         "docker-compose.yml has no healthcheck for the web service. "
         "A crashed Django process is not detected until a user reports an error. "
         "Add GET /health/ that checks DB connectivity, Redis ping, and returns 200/503."),
    ]

    for sev, title, detail in gaps:
        story.append(issue_block(sev, title, "Observability gap", detail, detail, "", "", S))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 11 — TOP RISKS & BREACH VECTORS
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("11. Top Risks, Breach Vectors & Failure Modes", S["h1"]))
    story.append(hr(S))

    story.append(Paragraph("Financial Fraud Vectors", S["h2"]))
    fraud = [
        "POST forged B2C callback to /mpesa/b2c/result/ → platform credits fake disbursement (no sig validation)",
        "Submit duplicate STK callback within 1-second window → dual credit if idempotency key collides",
        "Brute-force PIN via distributed attempt below lockout threshold → account takeover",
        "Exploit IDOR on CommunityContributionsView to enumerate all community finances",
        "Inject arbitrary amount into STK Push body (float vs Decimal rounding exploitable)",
        "Replay expired JWT with modified stage claim (if token blacklist has gap)",
    ]
    for item in fraud:
        story.append(Paragraph(f"• {item}", S["bullet"]))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("Financial Corruption Scenarios", S["h2"]))
    corrupt = [
        "Welfare contribution Celery retry fires after >1s → double LedgerEntry, inflated fund balance",
        "PaymentService.create_payment() used for manual reconciliation → LedgerEntry never written → "
        "permanent divergence between contribution.current_amount and ledger sum",
        "B2C disbursement fails → WelfareFund.balance decremented but never restored → "
        "'insufficient balance' blocks legitimate future disbursements",
        "CASCADE delete of User cascades to Contribution, LedgerEntry, DisbursementRequest → "
        "entire community's financial history deleted",
        "User deactivated mid-standing-order cycle → standing order fires but contribution check fails → "
        "ROSCA rotation skips participant silently",
        "AmendmentService._apply() sets fields directly without state machine protection → "
        "concurrent amendment and contribution creates inconsistent state",
    ]
    for item in corrupt:
        story.append(Paragraph(f"• {item}", S["bullet"]))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("Infrastructure Failure Modes", S["h2"]))
    infra = [
        "Redis goes down → OTP cache cleared → all in-flight authentication fails; "
        "PIN lockout state cleared → lockouts lifted; Celery broker down → all tasks queue locally and are lost on restart",
        "Database connection pool exhausted (no PgBouncer) → 503 cascade under moderate load spike",
        "Celery financial worker OOM on reconcile_balances → task silently fails; "
        "balance discrepancies accumulate undetected",
        "M-Pesa Daraja API outage → STK Push fails; B2C retries accumulate; "
        "after outage resolves, all retries fire simultaneously and may exceed rate limits",
        "Shared Redis for broker + cache → large Celery job queue evicts cache keys → "
        "OTP lookups return None → all authentications fail",
    ]
    for item in infra:
        story.append(Paragraph(f"• {item}", S["bullet"]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 12 — EVOLUTION ROADMAP
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("12. Architectural Evolution Roadmap", S["h1"]))
    story.append(hr(S))

    stages = [
        ("Phase 1: Fix Blockers (Week 1)", [
            "Add financial to Celery worker queue list (docker-compose.yml)",
            "Fix B2C retry logic — move _handle_payout_failure() to on_failure hook",
            "Add africastalking to requirements.txt",
            "Fix STK callback bare except — capture exception, log to Sentry, retry task",
            "Fix welfare and advance repayment idempotency keys (remove wall clock)",
            "Add LedgerEntry write to PaymentService.create_payment()",
            "Fix ContributionJoinRequest duplicate __str__ method",
            "Fix tests — correct exception types, method names, expected states",
            "Add M-Pesa IP allowlist + request logging at nginx level",
        ]),
        ("Phase 2: Security Hardening (Week 2-3)", [
            "Apply ScopedRateThrottle with pin_login scope to PINLoginView",
            "Move PIN to request body; exclude from all logging",
            "Implement WebSocket ticket exchange (replace ?token= query param)",
            "Add HMAC signature validation to all M-Pesa webhook views",
            "Fix IDOR — add membership check to CommunityContributionsView and ContributionPaymentsView",
            "Change User FK on_delete to PROTECT or SET_NULL everywhere",
            "Fix Notification model IntegerFields → ForeignKey(null=True, on_delete=SET_NULL)",
        ]),
        ("Phase 3: Reliability & Observability (Week 3-5)", [
            "Separate Redis broker from Redis cache (two Redis instances)",
            "Add Prometheus metrics: payment success rate, disbursement lag, queue depth",
            "Implement dead-letter queue for financial tasks + PagerDuty alert",
            "Add structured logging with structlog (payment_id, community_id as fields)",
            "Move migrate out of container entrypoint into init container",
            "Add GET /health/ endpoint with DB + Redis connectivity check",
            "Cache M-Pesa access token in Redis (3500s TTL)",
            "Add re-validation of membership in WebSocket receive()",
        ]),
        ("Phase 4: Performance (Week 5-8)", [
            "Add pagination to DiscoverCommunities, OpenContributions, WelfareActivity",
            "Fix N+1 in ContributionSerializer with annotate() and prefetch_related()",
            "Rewrite reconcile_balances as a SQL aggregation query with keyset pagination",
            "Add last_activity_at field to Community; replace 4-JOIN annotation",
            "Add message size limit to WebSocket consumer",
            "Add typing indicator debounce (2s minimum interval)",
            "Migrate WebSocket consumer ORM calls to Django async ORM (acreate, afilter)",
            "Add DB indexes: LedgerEntry(contribution_id, entry_date), Notification(user_id, is_read)",
        ]),
        ("Phase 5: Scale Preparation (Month 2-3)", [
            "Introduce PgBouncer for connection pooling",
            "Implement transactional outbox pattern for notification delivery",
            "Add Redis sorted set for community activity feed ordering",
            "Separate Celery worker processes per queue (financial workers isolated)",
            "Consider read replicas for analytical queries (reconciliation, reporting)",
            "Implement M-Pesa webhook signature validation with Safaricom public key",
            "Add end-to-end tests against M-Pesa sandbox in CI",
        ]),
    ]

    for stage_title, items in stages:
        story.append(Paragraph(stage_title, S["h2"]))
        for item in items:
            story.append(Paragraph(f"• {item}", S["bullet"]))
        story.append(Spacer(1, 0.2*cm))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════════════════
    # APPENDIX — ADDITIONAL ISSUES
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Appendix: Additional Issues", S["h1"]))
    story.append(hr(S))

    additional = [
        ("MEDIUM", "PINService.set_pin() double-saves the user",
         "apps/users/services.py:PINService.set_pin()",
         "Calls user.set_pin(pin) which calls user.save(), then calls user.is_pin_set=True; user.save() again.",
         "Two database writes per PIN set operation. Second write overwrites the first with a "
         "slightly stale user state if any concurrent modification occurred between the two saves.",
         "Remove the redundant is_pin_set = True; user.save() from PINService.set_pin(). "
         "The User.set_pin() method already sets is_pin_set = True and saves.",
         None),
        ("MEDIUM", "asgi.py hardcodes production settings module",
         "config/asgi.py — os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')",
         "ASGI entrypoint unconditionally sets the settings module to production. "
         "Any test that imports the ASGI application picks up production settings.",
         "WebSocket tests in CI connect to production Redis and production DB if env vars are set. "
         "Or they fail silently if production env vars are absent.",
         "Use DJANGO_SETTINGS_MODULE from the environment, do not setdefault to production. "
         "Let the deployment orchestrator set the correct module.",
         None),
        ("LOW", "AmendmentService._apply() bypasses state machine",
         "apps/contributions/services.py:AmendmentService._apply()",
         "Directly sets contribution fields without going through Contribution.transition_to(). "
         "No optimistic locking; no state validation.",
         "A concurrent amendment and contribution could produce an inconsistent state. "
         "The amendment silently overwrites a contribution that was updated between the "
         "amendment vote and its application.",
         "Wrap _apply() in select_for_update() on the Contribution row. "
         "Validate that the contribution is in an ACTIVE state before applying.",
         None),
        ("LOW", "M-Pesa STKPushView uses float() for amount",
         "apps/mpesa/views.py:STKPushView — amount = float(request.data.get('amount'))",
         "IEEE 754 floating-point representation causes rounding for values like 100.10.",
         "M-Pesa amount sent as 100.09999999... Safaricom may reject or round unpredictably. "
         "Financial amounts must never pass through float.",
         "Use Decimal: amount = Decimal(str(request.data.get('amount'))). "
         "Validate with a Serializer field: DecimalField(max_digits=10, decimal_places=2).",
         None),
        ("LOW", "M-Pesa C2B reconciliation uses ambiguous 9-digit phone suffix matching",
         "apps/mpesa/services.py:reconcile_c2b() — phone_number__endswith=phone[-9:]",
         "Phone numbers in Africa are not globally unique on their last 9 digits.",
         "Two users with phone numbers differing only in country code match the same suffix. "
         "Payment credited to wrong account.",
         "Normalize all phone numbers to E.164 format at storage time (+254XXXXXXXXX). "
         "Match on the full normalized number. Use a phone normalization library (phonenumbers).",
         None),
    ]

    for sev, title, location, root_cause, impact, fix, redesign in additional:
        story.append(issue_block(sev, title, location, root_cause, impact, fix, redesign, S))

    # ═══════════════════════════════════════════════════════════════════════════
    # FOOTER
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Spacer(1, 2*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ACCENT, spaceAfter=12))
    story.append(Paragraph(
        "WEPL Pre-Production Engineering Audit",
        ParagraphStyle("footer_title", fontSize=11, textColor=C_DARK,
                       fontName="Helvetica-Bold", alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        f"Generated {date.today().strftime('%B %d, %Y')} · CONFIDENTIAL · Engineering Leadership Only",
        ParagraphStyle("footer_sub", fontSize=9, textColor=grey,
                       fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4)
    ))
    story.append(Paragraph(
        "This document contains a complete audit of the WEPL codebase as reviewed. "
        "All findings reflect the state of the code at time of review. "
        "Re-audit recommended after each phase of remediation.",
        ParagraphStyle("footer_note", fontSize=8, textColor=grey,
                       fontName="Helvetica-Oblique", alignment=TA_CENTER)
    ))

    def add_page_number(canvas, doc):
        if doc.page > 1:  # skip cover
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(HexColor("#94a3b8"))
            canvas.drawRightString(
                PAGE_W - 2*cm, 1.2*cm,
                f"WEPL Audit Report  ·  Page {doc.page}"
            )
            canvas.restoreState()

    doc.build(story, onLaterPages=add_page_number, onFirstPage=add_page_number)
    print("PDF generated: WEPL_Audit_Report.pdf")


if __name__ == "__main__":
    build_report()
