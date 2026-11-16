from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    techpack_id = fields.Many2one("zyra.techpack", string="Tech Pack", index="btree_not_null", copy=True)

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        if self.techpack_id:
            values["techpack_id"] = self.techpack_id.id
        return values


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _get_custom_move_fields(self):
        return super()._get_custom_move_fields() + ["techpack_id"]

    def _get_matching_bom(self, product_id, company_id, values):
        techpack_id = values.get("techpack_id")
        if techpack_id and not values.get("bom_id"):
            techpack = self.env["zyra.techpack"].browse(techpack_id).exists()
            if techpack.bom_id and techpack.bom_id.product_tmpl_id == product_id.product_tmpl_id:
                return techpack.bom_id
        return super()._get_matching_bom(product_id, company_id, values)

    def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_dest_id, name, origin, company_id,
                         values, bom):
        vals = super()._prepare_mo_vals(product_id, product_qty, product_uom, location_dest_id, name, origin,
                                        company_id, values, bom)
        if values.get("techpack_id"):
            vals["techpack_id"] = values["techpack_id"]
        return vals
