from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "zyra")
class TestGarmentSuite(TransactionCase):

    def _suite(self):
        return self.env["ir.module.module"].search([("name", "=", "zyra_garment_suite")])

    def test_installing_suite_installs_every_garment_module(self):
        wanted = set(self._suite().dependencies_id.mapped("name"))
        installed = set(self.env["ir.module.module"].search(
            [("name", "in", list(wanted)), ("state", "=", "installed")]).mapped("name"))
        self.assertEqual(wanted - installed, set())
        # every zyra module on disk that is installed is part of the suite
        others = self.env["ir.module.module"].search([
            ("name", "=like", "zyra\\_%"), ("state", "=", "installed"),
            ("name", "!=", "zyra_garment_suite")])
        self.assertEqual(set(others.mapped("name")) - wanted, set())

    def test_suite_is_the_only_garment_application(self):
        apps = self.env["ir.module.module"].search([
            ("name", "=like", "zyra\\_%"), ("application", "=", True)])
        self.assertEqual(apps.mapped("name"), ["zyra_garment_suite"])

    def test_top_menu_is_named_garment_suite(self):
        menu = self.env.ref("zyra_garment_base.menu_garment_root")
        self.assertEqual(menu.name, "Garment Suite")
        self.assertFalse(menu.parent_id)
