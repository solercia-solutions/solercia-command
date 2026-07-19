"""RED tests for the GLPI assignee-matching cascade (change 17-adapter-glpi,
specs/user-homologation/spec.md, UH-R2). PURE functions — no DB, no HTTP:
``org_users``/``existing_link`` are plain in-memory ORM instances,
constructed WITHOUT ever touching a session (SQLAlchemy models are usable
as plain Python objects when never added to a session).
"""

import uuid

# Pulls in EVERY ORM model (including `Role`) so `User`'s string-based
# `relationship("Role", ...)` resolves when SQLAlchemy configures mappers —
# same reason `tests/conftest.py`'s `engine` fixture imports this first.
# This test never touches a DB session; only the class registry matters.
import app.db_init  # noqa: F401
from app.integrations.dtos import ExternalPerson
from app.modules.glpi_sync.models import GlpiUserLink
from app.modules.users.models import User
from app.shared.enums import MatchMethod


def _user(
    *,
    email: str | None = None,
    numero_documento: str | None = None,
    primer_nombre: str = "Ana",
    segundo_nombre: str | None = None,
    primer_apellido: str = "Torres",
    segundo_apellido: str | None = None,
) -> User:
    return User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4().hex[:8]}@example.com",
        primer_nombre=primer_nombre,
        segundo_nombre=segundo_nombre,
        primer_apellido=primer_apellido,
        segundo_apellido=segundo_apellido,
        numero_documento=numero_documento,
        hashed_password="x",
    )


def _person(
    *,
    external_id: str = "55",
    display_name: str | None = "Ana Torres",
    email: str | None = None,
    document: str | None = None,
) -> ExternalPerson:
    return ExternalPerson(
        external_id=external_id, display_name=display_name, email=email, document=document
    )


class TestNormalizationHelpers:
    def test_norm_email_lowercases_and_strips_whitespace(self) -> None:
        from app.modules.glpi_sync.service import norm_email

        assert norm_email("  Ana.Torres@Example.COM  ") == "ana.torres@example.com"

    def test_norm_doc_keeps_only_digits(self) -> None:
        from app.modules.glpi_sync.service import norm_doc

        assert norm_doc("1.234.567-8") == "12345678"
        assert norm_doc("CC 98.765.432") == "98765432"

    def test_norm_name_strips_accents_case_and_collapses_whitespace(self) -> None:
        from app.modules.glpi_sync.service import norm_name

        assert norm_name("  José  María   PÉREZ  ") == "jose maria perez"
        assert norm_name("Ana Torres") == "ana torres"


class TestEmailMatchAutoConfirms:
    def test_exact_normalized_email_match_auto_confirms_without_document_or_name(
        self,
    ) -> None:
        """Scenario: Match por correo auto-confirma."""

        from app.modules.glpi_sync.service import match_assignee

        target_user = _user(email="ana.torres@example.com", numero_documento="999999999")
        other_user = _user(email="carlos@example.com")
        person = _person(email="  Ana.Torres@EXAMPLE.com  ", document="000000000")

        result = match_assignee(person, [other_user, target_user], existing_link=None)

        assert result.matched_user_id == target_user.id
        assert result.match_method == MatchMethod.email
        assert result.candidates == ()


class TestDocumentMatchAutoConfirms:
    def test_exact_document_match_auto_confirms_when_no_email_match(self) -> None:
        """Scenario: Match por documento auto-confirma."""

        from app.modules.glpi_sync.service import match_assignee

        target_user = _user(email="no-match@example.com", numero_documento="123456789")
        person = _person(email="unrelated@example.com", document="123.456.789")

        result = match_assignee(person, [target_user], existing_link=None)

        assert result.matched_user_id == target_user.id
        assert result.match_method == MatchMethod.document
        assert result.candidates == ()


class TestNameMatchNeverAutoConfirms:
    def test_similar_name_without_email_or_document_only_suggests(self) -> None:
        """Scenario: Sin correo ni documento, el nombre solo sugiere."""

        from app.modules.glpi_sync.service import match_assignee

        target_user = _user(
            email="unrelated@example.com",
            numero_documento="000111222",
            primer_nombre="Ana",
            primer_apellido="Torres",
        )
        person = _person(display_name="Ana Torres", email=None, document=None)

        result = match_assignee(person, [target_user], existing_link=None)

        assert result.matched_user_id is None
        assert result.match_method is None
        assert len(result.candidates) == 1
        assert result.candidates[0].user_id == target_user.id
        assert result.candidates[0].reason == "name"
        assert result.candidates[0].score > 0.9

    def test_homonyms_both_appear_as_candidates_and_stay_pending(self) -> None:
        """Scenario: Homónimos nunca auto-confirman."""

        from app.modules.glpi_sync.service import match_assignee

        user_a = _user(
            email="ana.a@example.com", primer_nombre="Ana", primer_apellido="Torres"
        )
        user_b = _user(
            email="ana.b@example.com", primer_nombre="Ana", primer_apellido="Torres"
        )
        person = _person(display_name="Ana Torres", email=None, document=None)

        result = match_assignee(person, [user_a, user_b], existing_link=None)

        assert result.matched_user_id is None
        candidate_ids = {c.user_id for c in result.candidates}
        assert candidate_ids == {user_a.id, user_b.id}

    def test_unrelated_name_produces_no_candidates(self) -> None:
        """Triangulation: a completely dissimilar name yields zero
        candidates rather than a spurious low-score suggestion."""

        from app.modules.glpi_sync.service import match_assignee

        target_user = _user(primer_nombre="Zacarías", primer_apellido="Uribe")
        person = _person(display_name="Ana Torres", email=None, document=None)

        result = match_assignee(person, [target_user], existing_link=None)

        assert result.matched_user_id is None
        assert result.candidates == ()


class TestExistingLinkSkipsCascade:
    def test_existing_link_for_glpi_user_id_skips_the_whole_cascade(self) -> None:
        """Scenario: link ya existente se salta la cascada completa."""

        from app.modules.glpi_sync.service import match_assignee

        linked_user_id = uuid.uuid4()
        existing_link = GlpiUserLink(
            id=uuid.uuid4(),
            connector_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            glpi_user_id="55",
            user_id=linked_user_id,
            match_method=MatchMethod.email,
        )
        # Even a PERFECT email match on another user must be ignored: an
        # existing link short-circuits before any comparison runs.
        other_user = _user(email="ana.torres@example.com")
        person = _person(email="ana.torres@example.com")

        result = match_assignee(person, [other_user], existing_link=existing_link)

        assert result.skipped is True
        assert result.matched_user_id == linked_user_id
        assert result.match_method is None
        assert result.candidates == ()
