from odoo import api, fields, models


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    garment_role = fields.Selection([("colour", "Garment Colourway"), ("size", "Garment Size")],
                                    help="Set on the attributes created from garment styles.")
    garment_size_range_id = fields.Many2one("garment.size.range", string="Garment Size Range")


class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"

    garment_colour_id = fields.Many2one("garment.colour", string="Garment Colourway", index=True)
    garment_size_id = fields.Many2one("garment.size", string="Garment Size", index=True)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    garment_style_id = fields.Many2one("garment.style", string="Garment Style", index=True, copy=False)


class ProductProduct(models.Model):
    _inherit = "product.product"

    garment_colour_id = fields.Many2one("garment.colour", string="Colourway", compute="_compute_garment_cell",
                                        store=True, index=True)
    garment_size_id = fields.Many2one("garment.size", string="Size", compute="_compute_garment_cell",
                                      store=True, index=True)

    @api.depends("product_template_attribute_value_ids.product_attribute_value_id.garment_colour_id",
                 "product_template_attribute_value_ids.product_attribute_value_id.garment_size_id")
    def _compute_garment_cell(self):
        for product in self:
            values = product.product_template_attribute_value_ids.product_attribute_value_id
            product.garment_colour_id = values.garment_colour_id[:1]
            product.garment_size_id = values.garment_size_id[:1]
