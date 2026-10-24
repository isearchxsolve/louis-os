from __future__ import annotations

import unittest

from pathlib import Path
from scripts.sync_cash_first_ledger import synchronize, publication_changed


class CashFirstLedgerSyncTests(unittest.TestCase):
    def test_syncs_pipeline_without_inventing_submission_or_revenue(self) -> None:
        ledger = {
            "external_actions_submitted": 0,
            "internet_actions_submitted": 0,
            "conversions": 0,
            "revenue_confirmed_eur": 0.0,
            "revenue_received": 0.0,
        }
        portfolio = {
            "generated_at": "2026-07-27T08:00:00+00:00",
            "counts": {"cash_first": 3, "strategic": 10, "human_action_ready": 1},
            "top_cash_first": {"opportunity_id": "market-one", "reward_amount": 40.0, "currency": "USD"},
        }
        human = {"new_count": 1, "notification_required": True}
        cycle = {
            "generated_at": "2026-07-27T08:01:00+00:00",
            "simple_mission_sources_refreshed": ["freelancer_public_simple_jobs", "freelancer_public_software_jobs"],
            "simple_mission_opportunities_observed": 5,
            "simple_mission_dossiers_prepared": 1,
            "software_micro_mission_engine": "active",
            "software_micro_mission_capability_count": 5,
            "software_micro_mission_validated_demo_count": 3,
            "software_micro_missions_matched": 4,
            "software_micro_missions_accepted": 2,
            "software_micro_missions_rejected": 2,
            "software_micro_mission_dossiers_prepared": 1,
            "next_action": "notify_owner_and_complete_exact_human_gate",
        }
        result = synchronize(ledger, portfolio, human, cycle)
        self.assertEqual(result["cash_first_candidates"], 3)
        self.assertEqual(result["human_action_ready"], 1)
        self.assertEqual(result["simple_mission_dossiers_prepared"], 1)
        self.assertEqual(result["software_micro_mission_engine"], "active")
        self.assertEqual(result["software_micro_mission_capability_count"], 5)
        self.assertEqual(result["software_micro_mission_validated_demo_count"], 3)
        self.assertEqual(result["software_micro_missions_accepted"], 2)
        self.assertEqual(result["software_micro_mission_dossiers_prepared"], 1)
        self.assertEqual(result["external_actions_submitted"], 0)
        self.assertEqual(result["internet_actions_submitted"], 0)
        self.assertEqual(result["conversions"], 0)
        self.assertEqual(result["revenue_confirmed_eur"], 0.0)
        self.assertIsNone(result["net_profit_eur"])
        self.assertEqual(result["cost_basis_status"], "incomplete_cost_basis")
        self.assertIn("gcp_compute", result["unknown_cost_components"])

    def test_preserves_existing_receipt_backed_totals(self) -> None:
        ledger = {
            "external_actions_submitted": 2,
            "internet_actions_submitted": 2,
            "conversions": 1,
            "revenue_confirmed_eur": 12.5,
            "revenue_received": 12.5,
        }
        result = synchronize(ledger, {"counts": {}}, {}, {})
        self.assertEqual(result["external_actions_submitted"], 2)
        self.assertEqual(result["conversions"], 1)
        self.assertEqual(result["revenue_confirmed_eur"], 12.5)
        self.assertIsNone(result["net_profit_eur"])

    def test_computes_net_profit_only_with_complete_cost_basis(self) -> None:
        ledger = {"revenue_confirmed_eur": 12.5, "revenue_received": 12.5}
        costs = {
            "components": {
                "gcp_compute": {"known": True, "eur": 1.0},
                "model_api": {"known": True, "eur": 0.5},
                "github_actions": {"known": True, "eur": 0.0},
                "transaction_fees": {"known": True, "eur": 0.25},
            }
        }
        result = synchronize(ledger, {"counts": {}}, {}, {}, costs)
        self.assertEqual(result["cost_basis_status"], "complete")
        self.assertEqual(result["known_operating_cost_eur"], 1.75)
        self.assertEqual(result["net_profit_eur"], 10.75)
        self.assertEqual(result["unknown_cost_components"], [])

    def test_aggregate_wallet_receipt_does_not_require_individual_attribution(self) -> None:
        ledger = {
            "payouts_queued": 3,
            "payouts_received_verified": 0,
            "rustchain_aggregate_wallet_settlement_verified": True,
            "crypto_payment_verified": True,
            "revenue_confirmed_eur": 0.0,
        }
        result = synchronize(
            ledger,
            {"counts": {}},
            {},
            {"next_action": "route_top_cash_first_mission_to_executor"},
        )
        self.assertIn("aggregate crypto receipt", result["next_action"])
        self.assertIn("without assigning it to individual payouts", result["next_action"])
        self.assertEqual(result["payouts_received_verified"], 0)
        self.assertEqual(result["revenue_confirmed_eur"], 0.0)

    def test_queued_payout_keeps_priority_over_new_discovery_candidate(self) -> None:
        ledger = {
            "payouts_queued": 3,
            "payouts_received_verified": 0,
            "last_external_outcome_reconciliation": "2026-08-23T17:54:00+00:00",
            "revenue_confirmed_eur": 0.0,
        }
        cycle = {
            "generated_at": "2026-08-23T13:49:00+00:00",
            "next_action": "route_top_cash_first_mission_to_executor",
        }
        result = synchronize(ledger, {"counts": {}}, {}, cycle)
        self.assertEqual(result["updated_at"], "2026-08-23T17:54:00+00:00")
        self.assertIn("RTC wallet", result["next_action"])


    def test_publication_ignores_scan_time_preparation_and_action_wording(self) -> None:
        old = {"revenue_confirmed_eur": 0, "updated_at": "old", "cash_first_candidates": 1}
        new = {**old, "updated_at": "new", "cash_first_candidates": 12,
               "simple_mission_dossiers_prepared": 4, "next_action": "changed wording"}
        self.assertFalse(publication_changed(old, new))
        self.assertFalse(publication_changed(new, new))

    def test_publication_detects_economic_and_cost_changes_without_zero_filling(self) -> None:
        for field, value in (
            ("external_actions_submitted", 1), ("external_actions_accepted", 1),
            ("revenue_confirmed_eur", 1.0), ("payouts_received_verified", 1),
            ("known_operating_cost_eur", 2.0), ("cost_basis_status", "complete"),
        ):
            with self.subTest(field=field):
                self.assertTrue(publication_changed({field: 0}, {field: value}))
        self.assertTrue(publication_changed({}, {"revenue_confirmed_eur": 0}))

    def test_publication_requires_new_exact_human_gate(self) -> None:
        gate = {"owner_notification_required": True, "new_human_actions": 1,
                "cash_first_top_opportunity": {
                    "opportunity_id": "one", "notification_fingerprint": "exact"}}
        self.assertTrue(publication_changed({}, gate))
        self.assertFalse(publication_changed(gate, gate))
        self.assertFalse(publication_changed({}, {**gate, "new_human_actions": 0}))
        self.assertFalse(publication_changed({}, {**gate, "owner_notification_required": False}))

    def test_workflow_gates_publication_and_never_comments_saturated_issue(self) -> None:
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/cash-first-ledger-sync.yml").read_text()
        self.assertIn("gh issue comment 473", workflow)
        self.assertNotIn("gh issue comment 77", workflow)
        self.assertIn("if: steps.synchronize.outputs.publish == 'true'", workflow)
        self.assertIn("publication_changed(previous, current)", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertLess(workflow.index("- name: Persist dashboard ledger"),
                        workflow.index("- name: Publish material synchronized truth"))


if __name__ == "__main__":
    unittest.main()
