from odoo import api, models


class GarmentShippingDemo(models.AbstractModel):
    _name = "garment.shipping.demo"
    _description = "Packing and shipping demo loader"

    @api.model
    def _load_demo(self):
        return True
