from odoo.tests import tagged

from .common import TechpackCase


@tagged("post_install", "-at_install", "zyra")
class TestBomVariants(TechpackCase):

    def test_generate_variants_makes_one_variant_per_colourway_and_size(self):
        self.style.action_generate_variants_bom()
        template = self.style.product_tmpl_id
        self.assertTrue(template)
        self.assertEqual(template.garment_style_id, self.style)
        self.assertEqual(self.style.variant_count, 8)
        variant = self.style._get_variant(self.white, self.l)
        self.assertEqual(variant.garment_colour_id, self.white)
        self.assertEqual(variant.garment_size_id, self.l)
        self.assertFalse(self.style.bom_id, "no BoM before the tech pack is approved")

    def test_generate_variants_twice_does_not_duplicate(self):
        self.style.action_generate_variants_bom()
        self.style.action_generate_variants_bom()
        self.assertEqual(self.style.variant_count, 8)

    def test_new_colourway_adds_variants(self):
        self.style.action_generate_variants_bom()
        black = self.env["garment.colour"].create({"name": "Test Black", "code": "TBK"})
        self.style.colour_ids = [(4, black.id)]
        self.style.action_generate_variants_bom()
        self.assertEqual(self.style.variant_count, 12)

    def test_approval_generates_bom_with_wastage_per_colourway_and_size(self):
        self.approve(self.techpack)
        bom = self.techpack.bom_id
        self.assertTrue(bom)
        self.assertEqual(bom.techpack_id, self.techpack)
        self.assertEqual(self.style.bom_id, bom)
        self.assertEqual(bom.product_tmpl_id, self.style.product_tmpl_id)
        self.assertEqual(len(bom.bom_line_ids), 4)

        def components(colour, size):
            variant = self.style._get_variant(colour, size)
            lines = bom.bom_line_ids.filtered(lambda ln: not ln._skip_bom_line(variant))
            return {(ln.product_id, round(ln.product_qty, 4)) for ln in lines}

        self.assertEqual(components(self.navy, self.m), {(self.fabric, 1.26), (self.label, 1.0)})
        self.assertEqual(components(self.white, self.m), {(self.fabric, 1.1), (self.label, 1.0)})
        self.assertEqual(components(self.white, self.xl),
                         {(self.fabric, 1.1), (self.label, 1.0), (self.button, 3.0)})

    def test_new_approved_revision_archives_the_old_bom(self):
        self.approve(self.techpack)
        old_bom = self.techpack.bom_id
        v2 = self.env["zyra.techpack"].browse(self.techpack.action_new_revision()["res_id"])
        v2.bom_line_ids.filtered(lambda ln: ln.colour_id == self.navy).consumption = 1.0
        self.approve(v2)
        self.assertNotEqual(v2.bom_id, old_bom)
        self.assertFalse(old_bom.active)
        self.assertTrue(v2.bom_id.active)
        variant = self.style._get_variant(self.navy, self.s)
        found = self.env["mrp.bom"]._bom_find(variant)[variant]
        self.assertEqual(found, v2.bom_id)
