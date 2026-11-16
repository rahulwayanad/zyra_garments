from datetime import timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import MerchCase


@tagged("post_install", "-at_install", "zyra")
class TestApprovals(MerchCase):

    def _card(self, **vals):
        return self.env["garment.approval"].create(dict({
            "style_id": self.style.id, "kind": "lab_dip", "colour_id": self.red.id,
            "decision_due": self.today + timedelta(days=7),
            "option_ids": [Command.create({"name": n, "hex": h}) for n, h in (("A", "#aa0000"), ("B", "#bb0000"))],
        }, **vals))

    def test_sending_a_card_counts_the_submission(self):
        card = self._card()
        card.action_send()
        self.assertEqual((card.state, card.submission, card.sent_date), ("with_buyer", 1, self.today))
        card.action_ask_resubmission()
        self.assertEqual(card.state, "resubmit")
        card.action_send()
        self.assertEqual(card.submission, 2)

    def test_approval_needs_the_option_the_buyer_chose(self):
        card = self._card()
        card.action_send()
        with self.assertRaises(UserError):
            card.action_approve()
        card.chosen_option_id = card.option_ids.filtered(lambda o: o.name == "A")
        card.action_approve()
        self.assertEqual(card.state, "approved")
        self.assertEqual(card.decision_date, self.today)

    def test_card_without_options_can_be_approved_directly(self):
        card = self._card(kind="trim_card", option_ids=False)
        card.action_send()
        card.action_approve()
        self.assertEqual(card.state, "approved")

    def test_options_sent_text_names_every_option_and_the_colour(self):
        card = self._card()
        self.assertEqual(card.options_sent, "A and B against Merch Red")
        self.assertIn("#aa0000", card.swatch_html)

    def test_days_to_approval_counts_from_first_submission(self):
        card = self._card()
        card.action_send()
        card.first_sent_date = self.today - timedelta(days=9)
        card.chosen_option_id = card.option_ids[0]
        card.action_approve()
        self.assertEqual(card.days_to_approval, 9)

    def test_card_past_decision_due_and_not_approved_is_overdue(self):
        card = self._card(decision_due=self.today - timedelta(days=2))
        card.action_send()
        self.assertTrue(card.is_overdue)
        self.assertIn(card, self.env["garment.approval"].search([("is_overdue", "=", True)]))
        card.chosen_option_id = card.option_ids[0]
        card.action_approve()
        self.assertFalse(card.is_overdue)

    def test_other_open_cards_of_the_style_are_counted(self):
        card = self._card()
        self._card(kind="strike_off")
        done = self._card(kind="trim_card", option_ids=False)
        done.action_send()
        done.action_approve()
        self.assertEqual(card.other_open_count, 1)
