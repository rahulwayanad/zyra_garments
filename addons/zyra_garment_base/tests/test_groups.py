from odoo.tests import TransactionCase, tagged

OPERATIONAL_ROLES = [
    "merchandiser", "techpack_designer", "costing", "fabric_store", "cutting",
    "line_supervisor", "quality", "packing_shipping", "wages",
]


@tagged("post_install", "-at_install", "zyra")
class TestGarmentGroups(TransactionCase):

    def _group(self, role):
        return self.env.ref(f"zyra_garment_base.group_garment_{role}")

    def test_there_are_eleven_garment_roles_in_one_category(self):
        category = self.env.ref("zyra_garment_base.module_category_garment")
        groups = self.env["res.groups"].search([("category_id", "=", category.id)])
        self.assertEqual(len(groups), 11)

    def test_factory_manager_implies_every_operational_role(self):
        manager = self._group("factory_manager")
        for role in OPERATIONAL_ROLES:
            self.assertIn(self._group(role), manager.trans_implied_ids, role)

    def test_garment_admin_implies_factory_manager(self):
        self.assertIn(self._group("factory_manager"), self._group("admin").trans_implied_ids)

    def test_every_role_is_an_internal_user(self):
        for role in OPERATIONAL_ROLES + ["factory_manager", "admin"]:
            self.assertIn(self.env.ref("base.group_user"), self._group(role).trans_implied_ids, role)

    def test_fabric_store_gets_inventory_access(self):
        self.assertIn(self.env.ref("stock.group_stock_user"), self._group("fabric_store").trans_implied_ids)

    def test_user_given_factory_manager_holds_every_role(self):
        user = self.env["res.users"].create({
            "name": "Test Manager", "login": "zyra_test_manager",
            "groups_id": [(6, 0, [self._group("factory_manager").id])],
        })
        for role in OPERATIONAL_ROLES:
            self.assertTrue(user.has_group(f"zyra_garment_base.group_garment_{role}"), role)
        self.assertFalse(user.has_group("zyra_garment_base.group_garment_admin"))

    def test_merchandiser_cannot_edit_defect_library_but_quality_can(self):
        merch = self.env["res.users"].create({
            "name": "Test Merch", "login": "zyra_test_merch",
            "groups_id": [(6, 0, [self._group("merchandiser").id])],
        })
        quality = self.env["res.users"].create({
            "name": "Test QC", "login": "zyra_test_qc",
            "groups_id": [(6, 0, [self._group("quality").id])],
        })
        Defect = self.env["garment.defect"]
        self.assertTrue(Defect.with_user(merch).has_access("read"))
        self.assertFalse(Defect.with_user(merch).has_access("create"))
        self.assertTrue(Defect.with_user(quality).has_access("create"))
