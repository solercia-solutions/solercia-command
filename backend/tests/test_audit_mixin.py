"""Tests for ``AuditMixin`` (R4) — structural, no DB needed.

``created_by``/``updated_by`` are nullable UUID columns with a
``ON DELETE SET NULL`` foreign key to ``users.id``. Verified directly on the
mixin's declared columns (pre-mapping) so this test doesn't depend on which
concrete models mix it in yet.
"""

from sqlalchemy import Uuid

from app.shared.base_model import AuditMixin


def test_audit_mixin_declares_created_by_nullable_uuid_fk_to_users() -> None:
    column = AuditMixin.__dict__["created_by"].column

    assert isinstance(column.type, Uuid)
    assert column.nullable is True
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "users.id"
    assert foreign_keys[0].ondelete == "SET NULL"


def test_audit_mixin_declares_updated_by_nullable_uuid_fk_to_users() -> None:
    column = AuditMixin.__dict__["updated_by"].column

    assert isinstance(column.type, Uuid)
    assert column.nullable is True
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "users.id"
    assert foreign_keys[0].ondelete == "SET NULL"
