/** @odoo-module **/
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const BANDS = [
    { band: "1", label: _t("Up to 3 in"), pts: _t("1 pt") },
    { band: "2", label: _t("3 to 6 in"), pts: _t("2 pt") },
    { band: "3", label: _t("6 to 9 in"), pts: _t("3 pt") },
    { band: "4", label: _t("Over 9 in"), pts: _t("4 pt") },
];

/**
 * Tablet screen on the inspection frame: tap the defect, then its length band; points per 100 sq yd and the
 * verdict update after every tap (computed on the server, so the formula lives in one place).
 */
export class FabricInspectionTablet extends Component {
    static template = "zyra_garment_materials.FabricInspectionTablet";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.bands = BANDS;
        const params = (this.props.action && this.props.action.params) || {};
        const ctx = (this.props.action && this.props.action.context) || {};
        this.state = useState({
            inspectionId: params.inspection_id || ctx.active_id || false,
            defects: [],
            defectId: false,
            data: null,
            queue: { inspections: [], rolls: [] },
            online: navigator.onLine,
            busy: false,
        });
        this._onOnline = () => (this.state.online = navigator.onLine);
        onWillStart(async () => {
            this.state.defects = await this.orm.call("garment.fabric.inspection", "tablet_defect_types", []);
            await this.load();
        });
        onMounted(() => {
            window.addEventListener("online", this._onOnline);
            window.addEventListener("offline", this._onOnline);
        });
        onWillUnmount(() => {
            window.removeEventListener("online", this._onOnline);
            window.removeEventListener("offline", this._onOnline);
        });
    }

    async load() {
        if (this.state.inspectionId) {
            this.state.data = await this.orm.call("garment.fabric.inspection", "tablet_state", [[this.state.inspectionId]]);
        } else {
            this.state.data = null;
            this.state.queue = await this.orm.call("garment.fabric.inspection", "tablet_queue", []);
        }
    }

    async run(method, args = []) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.data = await this.orm.call("garment.fabric.inspection", method, [[this.state.inspectionId], ...args]);
        } finally {
            this.state.busy = false;
        }
    }

    async openInspection(id) {
        this.state.inspectionId = id;
        await this.load();
    }

    async startRoll(lotId) {
        this.state.inspectionId = await this.orm.call("garment.fabric.inspection", "tablet_start", [lotId]);
        await this.load();
    }

    async backToQueue() {
        this.state.inspectionId = false;
        this.state.defectId = false;
        await this.load();
    }

    pickDefect(id) {
        this.state.defectId = this.state.defectId === id ? false : id;
    }

    async tapBand(band) {
        if (!this.state.defectId) {
            this.notification.add(_t("Pick the defect first."), { type: "warning" });
            return;
        }
        await this.run("tablet_add_defect", [this.state.defectId, band, this.state.data.current_yard]);
        this.state.defectId = false;
    }

    async moveYard(delta) {
        const yard = Math.max(0, Math.round((this.state.data.current_yard + delta) * 10) / 10);
        await this.run("tablet_set", [{ current_yard: yard }]);
    }

    async setNumber(field, ev) {
        const value = parseFloat(ev.target.value);
        if (!isNaN(value) && value >= 0) {
            await this.run("tablet_set", [{ [field]: value }]);
        }
    }

    async undo() {
        await this.run("tablet_undo");
    }

    async finish() {
        await this.run("tablet_finish");
        this.notification.add(_t("Roll %s: %s", this.state.data.roll, this.state.data.result_label), {
            type: this.state.data.result === "pass" ? "success" : "warning",
        });
    }

    openForm() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "garment.fabric.inspection",
            res_id: this.state.inspectionId,
            views: [[false, "form"]],
        });
    }

    get verdictClass() {
        const r = this.state.data && this.state.data.result;
        return r === "pass" ? "o_zyra_tab_good" : r === "reject" ? "o_zyra_tab_bad" : "o_zyra_tab_warn";
    }
}

registry.category("actions").add("zyra_fabric_inspection_tablet", FabricInspectionTablet);
