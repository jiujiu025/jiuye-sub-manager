from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.node import Node
from app.models.source import Source
from app.db import SessionLocal
from app.services.subscription_service import SubscriptionService
from app.utils.fingerprint import build_node_fingerprint


def test_expired_resource_is_excluded_from_package_nodes() -> None:
    db_session = SessionLocal()
    try:
        source = Source(
            name="expired-source",
            url="https://example.com/sub",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db_session.add(source)
        db_session.flush()
        node = Node(
            source_id=source.id,
            source_name=source.name,
            original_name="expired-node",
            name="expired-node",
            type="vless",
            server="198.51.100.10",
            port=443,
            source_type="upstream",
            node_category="subscription",
            enabled=True,
            expires_at=source.expires_at,
            node_fingerprint=build_node_fingerprint(
                node_type="vless", server="198.51.100.10", port=443
            ),
        )
        db_session.add(node)
        db_session.commit()

        assert db_session.query(Node).count() == 1
        assert not SubscriptionService(db_session).node_repo.list_enabled_with_filters()
    finally:
        db_session.rollback()
        db_session.close()
