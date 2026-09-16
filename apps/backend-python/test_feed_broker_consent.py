import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.services.feed_broker_consent import (
    build_consent_record,
    brokers_match,
    collect_mismatch_accounts,
)


class FeedBrokerConsentUnitTests(unittest.TestCase):
    def test_brokers_match_on_server(self):
        feed = {"meta_profile": {"server": "ICMarkets-Demo"}, "broker_type": "MT5", "market_type": "INTERNATIONAL"}
        same = {"meta_profile": {"server": "ICMarkets-Demo"}, "broker_type": "MT5", "market_type": "INTERNATIONAL"}
        other = {"meta_profile": {"server": "Exness-MT5"}, "broker_type": "MT5", "market_type": "INTERNATIONAL"}
        self.assertTrue(brokers_match(feed, same))
        self.assertFalse(brokers_match(feed, other))

    def test_collect_mismatch_accounts(self):
        feed = {
            "_id": "feed",
            "account_name": "Feed Acc",
            "meta_profile": {"server": "ICMarkets-Demo"},
            "broker_type": "MT5",
        }
        matched = {
            "_id": "a1",
            "account_name": "Same",
            "meta_profile": {"server": "ICMarkets-Demo"},
            "broker_type": "MT5",
        }
        mismatched = {
            "_id": "a2",
            "account_name": "Other",
            "meta_profile": {"server": "Exness-MT5"},
            "broker_type": "MT5",
        }
        result = collect_mismatch_accounts(feed_account=feed, execution_accounts=[matched, mismatched])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["account_id"], "a2")
        self.assertIn("Exness-MT5", result[0]["warning"])

    def test_build_consent_record(self):
        feed = {"_id": "feed", "account_name": "Feed", "meta_profile": {"server": "A"}}
        execution = {"_id": "exec", "account_name": "Exec", "meta_profile": {"server": "B"}}
        record = build_consent_record(
            feed_account=feed,
            execution_account=execution,
            warning_text="warn",
            agreed_at=datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(record["agreed"])
        self.assertEqual(record["feed_account_id"], "feed")
        self.assertEqual(record["execution_account_id"], "exec")
        self.assertEqual(record["warning_text"], "warn")
        self.assertTrue(record["agreed_at"].startswith("2026-07-25T12:00:00"))


class FeedBrokerConsentGateTests(unittest.TestCase):
    def test_enforce_requires_consent_on_mismatch(self):
        from app.main import _enforce_feed_broker_consent

        feed = {"_id": "feed", "meta_profile": {"server": "A"}, "broker_type": "MT5"}
        execution = [{"_id": "exec", "meta_profile": {"server": "B"}, "broker_type": "MT5"}]
        with self.assertRaises(HTTPException) as ctx:
            _enforce_feed_broker_consent(feed_account=feed, execution_accounts=execution, consented=False)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["code"], "FEED_BROKER_MISMATCH_CONSENT_REQUIRED")

    def test_enforce_allows_when_consented(self):
        from app.main import _enforce_feed_broker_consent, _consent_for_execution_account

        feed = {"_id": "feed", "account_name": "Feed", "meta_profile": {"server": "A"}, "broker_type": "MT5"}
        execution = {"_id": "exec", "account_name": "Exec", "meta_profile": {"server": "B"}, "broker_type": "MT5"}
        _enforce_feed_broker_consent(feed_account=feed, execution_accounts=[execution], consented=True)
        mismatch, consent = _consent_for_execution_account(
            feed_account=feed, execution_account=execution, consented=True
        )
        self.assertTrue(mismatch)
        self.assertTrue(consent["agreed"])

    def test_same_broker_does_not_require_consent(self):
        from app.main import _enforce_feed_broker_consent, _consent_for_execution_account

        feed = {"_id": "feed", "meta_profile": {"server": "A"}, "broker_type": "MT5"}
        execution = {"_id": "exec", "meta_profile": {"server": "A"}, "broker_type": "MT5"}
        _enforce_feed_broker_consent(feed_account=feed, execution_accounts=[execution], consented=False)
        mismatch, consent = _consent_for_execution_account(
            feed_account=feed, execution_account=execution, consented=False
        )
        self.assertFalse(mismatch)
        self.assertIsNone(consent)


class MarketDataStreamFeedRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_primary_tick_dispatches_trap_reversal(self):
        from app.services.market_data_stream import MarketDataStreamManager

        manager = MarketDataStreamManager.__new__(MarketDataStreamManager)
        manager._mongo_outage_until = {}
        manager._last_reconcile_at = {"user-1": datetime.now(timezone.utc)}
        manager._schedule_snapshot_update = MagicMock()

        session = {
            "user_id": "user-1",
            "account_db_id": "feed-acc",
            "account": {"_id": "feed-acc"},
            "kind": "primary",
            "db": MagicMock(),
        }
        price = {"symbol": "XAUUSD", "bid": 1.0, "ask": 1.1}

        with patch("app.services.market_data_stream.run_sync", new_callable=AsyncMock):
            with patch("app.services.market_data_stream.trap_reversal_manager") as trap_rev:
                trap_rev.handle_price = AsyncMock()
                with patch("app.services.market_data_stream.master_break_manager") as master_break:
                    master_break.handle_price = AsyncMock()
                    with patch("app.services.market_data_stream.run_coro_in_thread", new_callable=AsyncMock):
                        with patch("app.services.market_data_stream.manual_order_runtime_manager"):
                            with patch("app.services.market_data_stream.m1_candle_builder"):
                                with patch("app.services.market_data_stream.trade_planner_runtime_manager"):
                                    await manager._process_tick_work_locked("user-1", session, price)

                trap_rev.handle_price.assert_awaited()
                args = trap_rev.handle_price.await_args.args
                self.assertEqual(args[0], "XAUUSD")
                self.assertEqual(args[1], price)
                master_break.handle_price.assert_awaited()


if __name__ == "__main__":
    unittest.main()
