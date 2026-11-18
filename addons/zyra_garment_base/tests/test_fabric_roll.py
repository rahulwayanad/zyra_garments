from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "zyra")
class TestFabricRoll(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fabric = cls.env["product.product"].create({
            "name": "Test Twill 220 gsm", "is_storable": True, "tracking": "lot",
        })
        cls.roll = cls.env["stock.lot"].create({
            "name": "TEST-R001", "product_id": cls.fabric.id, "is_fabric_roll": True,
            "dye_lot": "DL-1", "shade_group": "A", "width_cm": 150, "gsm": 220,
        })
        cls.env.cr.precommit.run()  # post the creation message now

    def test_new_roll_starts_received(self):
        self.assertEqual(self.roll.roll_status, "received")

    def test_received_roll_can_be_approved(self):
        self.roll.action_roll_approve()
        self.assertEqual(self.roll.roll_status, "approved")

    def test_hold_keeps_the_reason_and_approve_clears_it(self):
        self.roll.action_roll_hold(reason="62 points over limit")
        self.assertEqual(self.roll.roll_status, "hold")
        self.assertEqual(self.roll.roll_hold_reason, "62 points over limit")
        self.roll.action_roll_approve()
        self.assertEqual(self.roll.roll_status, "approved")
        self.assertFalse(self.roll.roll_hold_reason)

    def test_rejected_roll_cannot_be_approved_directly(self):
        self.roll.action_roll_reject(reason="Holes")
        with self.assertRaises(UserError):
            self.roll.action_roll_approve()
        with self.assertRaises(UserError):
            self.roll.action_roll_hold()

    def test_only_factory_manager_can_release_a_rejected_roll(self):
        self.roll.action_roll_reject()
        store = self.env["res.users"].create({
            "name": "Store Keeper", "login": "zyra_test_store",
            "groups_id": [(6, 0, [self.env.ref("zyra_garment_base.group_garment_fabric_store").id])],
        })
        with self.assertRaises(UserError):
            self.roll.with_user(store).action_roll_reset()
        manager = self.env["res.users"].create({
            "name": "Floor Manager", "login": "zyra_test_fm",
            "groups_id": [(6, 0, [self.env.ref("zyra_garment_base.group_garment_factory_manager").id])],
        })
        self.roll.with_user(manager).action_roll_reset()
        self.assertEqual(self.roll.roll_status, "received")

    def test_status_change_is_logged_in_chatter(self):
        before = len(self.roll.message_ids)
        self.roll.action_roll_approve()
        self.env.cr.precommit.run()  # tracking messages are written at commit time
        self.roll.invalidate_recordset(["message_ids"])
        self.assertGreater(len(self.roll.message_ids), before)

    def test_plain_lot_is_not_a_roll(self):
        lot = self.env["stock.lot"].create({"name": "TEST-PLAIN", "product_id": self.fabric.id})
        with self.assertRaises(UserError):
            lot.action_roll_approve()

    def test_internal_users_see_lots_so_rolls_can_be_received(self):
        """Rule: fabric rolls are stock lots, so every internal user has Lots & Serial Numbers, even on a
        database created without demo data."""
        self.assertIn(self.env.ref("stock.group_production_lot"), self.env.ref("base.group_user").implied_ids)
        user = self.env["res.users"].create({"name": "Roll Receiver", "login": "roll_receiver"})
        self.assertTrue(user.has_group("stock.group_production_lot"))
