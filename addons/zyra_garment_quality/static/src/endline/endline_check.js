/** Tablet end-line check (screen 64): tap where, tap what, record. Every tap of "Good piece" or
 *  "Record defect" counts one piece on today's end-line inspection of the line; the hour and day DHU
 *  tiles refresh from the server after each tap. */
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const MODEL = "garment.inspection";

export class EndlineCheck extends Component {
    static template = "zyra_garment_quality.EndlineCheck";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            lines: [],
            lineId: false,
            data: null,
            position: false,
            defectId: false,
            busy: false,
            online: navigator.onLine,
            flash: false,
        });
        const ctx = (this.props.action && this.props.action.context) || {};
        const params = (this.props.action && this.props.action.params) || {};
        this.initialLine = params.line_id || ctx.line_id || false;
        this.onOnline = () => (this.state.online = true);
        this.onOffline = () => (this.state.online = false);
        onWillStart(async () => {
            if (this.initialLine) {
                await this.openLine(this.initialLine);
            } else {
                this.state.lines = await this.orm.call(MODEL, "garment_endline_lines", []);
                if (this.state.lines.length === 1) {
                    await this.openLine(this.state.lines[0].id);
                }
            }
        });
        onMounted(() => {
            window.addEventListener("online", this.onOnline);
            window.addEventListener("offline", this.onOffline);
        });
        onWillUnmount(() => {
            window.removeEventListener("online", this.onOnline);
            window.removeEventListener("offline", this.onOffline);
        });
    }

    async openLine(lineId) {
        this.state.data = await this.orm.call(MODEL, "garment_endline_state", [lineId]);
        this.state.lineId = lineId;
        this.state.position = false;
        this.state.defectId = false;
    }

    async backToLines() {
        this.state.lines = await this.orm.call(MODEL, "garment_endline_lines", []);
        this.state.lineId = false;
        this.state.data = null;
    }

    selectPosition(key) {
        this.state.position = this.state.position === key ? false : key;
    }

    selectDefect(id) {
        this.state.defectId = this.state.defectId === id ? false : id;
    }

    get canRecord() {
        return Boolean(this.state.position && this.state.defectId && !this.state.busy);
    }

    async record(good) {
        if (this.state.busy || (!good && !this.canRecord)) {
            return;
        }
        this.state.busy = true;
        try {
            const stats = await this.orm.call(MODEL, "garment_endline_record", [
                this.state.lineId,
                good ? false : this.state.defectId,
                good ? false : this.state.position,
            ]);
            this.state.data.stats = stats;
            this.state.flash = good ? "good" : "defect";
            setTimeout(() => (this.state.flash = false), 400);
            this.state.position = false;
            this.state.defectId = false;
        } catch (error) {
            this.notification.add(_t("Could not record the piece. Check the connection and tap again."), {
                type: "danger",
            });
            throw error;
        } finally {
            this.state.busy = false;
        }
    }

    dhuClass(value) {
        const limit = this.state.data.stats.limit || 0;
        if (!limit) {
            return "";
        }
        if (value > limit) {
            return "o_zyra_el_bad";
        }
        if (value >= limit * 0.8) {
            return "o_zyra_el_warn";
        }
        return "";
    }

    fmt(value) {
        return (Math.round((value || 0) * 10) / 10).toFixed(1) + "%";
    }
}

registry.category("actions").add("zyra_garment_endline_check", EndlineCheck);
