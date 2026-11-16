/** Size × colour grid of a production order (screen 34).
 *  Field widget on the `line_ids` one2many of garment.order: one row per colourway, one column per size,
 *  ordered quantity in each cell (editable while the order is draft or being amended) and three thin
 *  bars for cut / sewn / packed against the ordered quantity. */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { formatInteger } from "@web/views/fields/formatters";

function m2o(value) {
    if (!value) {
        return [false, ""];
    }
    if (Array.isArray(value)) {
        return value;
    }
    return [value.id, value.display_name];
}

export class SizeColourGrid extends Component {
    static template = "zyra_garment_merch.SizeColourGrid";
    static props = { ...standardFieldProps };

    get list() {
        return this.props.record.data[this.props.name];
    }

    get grid() {
        const records = [...this.list.records].sort(
            (a, b) => (a.data.sequence || 0) - (b.data.sequence || 0)
        );
        const sizes = new Map();
        const colours = new Map();
        const cells = {};
        for (const rec of records) {
            const [sizeId, sizeName] = m2o(rec.data.size_id);
            const [colourId, colourName] = m2o(rec.data.colour_id);
            if (!sizeId || !colourId) {
                continue;
            }
            if (!sizes.has(sizeId)) {
                sizes.set(sizeId, { id: sizeId, name: sizeName, seq: rec.data.size_sequence || 0, total: 0 });
            }
            if (!colours.has(colourId)) {
                colours.set(colourId, { id: colourId, name: colourName, hex: rec.data.colour_hex, total: 0 });
            }
            cells[`${colourId}-${sizeId}`] = rec;
            sizes.get(sizeId).total += rec.data.qty_ordered || 0;
            colours.get(colourId).total += rec.data.qty_ordered || 0;
        }
        const sizeList = [...sizes.values()].sort((a, b) => a.seq - b.seq || a.id - b.id);
        const rows = [...colours.values()].map((colour) => ({
            ...colour,
            cells: sizeList.map((size) => ({ key: `${colour.id}-${size.id}`, rec: cells[`${colour.id}-${size.id}`] })),
        }));
        const total = sizeList.reduce((sum, s) => sum + s.total, 0);
        return { sizes: sizeList, rows, total };
    }

    get editable() {
        return !this.props.readonly;
    }

    fmt(value) {
        return formatInteger(value || 0);
    }

    pct(rec, field) {
        const ordered = rec.data.qty_ordered || 0;
        if (!ordered) {
            return 0;
        }
        return Math.min(100, Math.round(((rec.data[field] || 0) * 100) / ordered));
    }

    onChange(rec, ev) {
        const value = parseInt(ev.target.value, 10);
        rec.update({ qty_ordered: Number.isNaN(value) || value < 0 ? 0 : value });
    }
}

registry.category("fields").add("zyra_size_colour_grid", {
    component: SizeColourGrid,
    displayName: "Size and colour grid",
    supportedTypes: ["one2many"],
});
