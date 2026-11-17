/** @odoo-module **/
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Full-screen TV board above a line (screen 56). Refreshes every minute. */
export class LineTvBoard extends Component {
    static template = "zyra_garment_sewing.LineTvBoard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        const params = (this.props.action && this.props.action.params) || {};
        const ctx = (this.props.action && this.props.action.context) || {};
        this.state = useState({ lines: [], lineId: params.line_id || ctx.active_id || false, data: null,
                                live: true });
        onWillStart(async () => {
            this.state.lines = await this.orm.searchRead("garment.line", [], ["name"]);
            if (!this.state.lineId && this.state.lines.length) {
                this.state.lineId = this.state.lines[0].id;
            }
            await this.load();
        });
        this.timer = setInterval(() => this.load(), 60000);
        onWillUnmount(() => clearInterval(this.timer));
    }

    async load() {
        if (!this.state.lineId) {
            return;
        }
        try {
            this.state.data = await this.orm.call("garment.line", "garment_tv_board", [[Number(this.state.lineId)]]);
            this.state.live = true;
        } catch {
            this.state.live = false;
        }
    }

    async onLine(ev) {
        this.state.lineId = Number(ev.target.value);
        await this.load();
    }

    barHeight(value) {
        return `${Math.round((value / this.state.data.max_bar) * 180)}px`;
    }

    hourOf(row) {
        return parseInt(row.hour.slice(0, 2), 10);
    }
}

registry.category("actions").add("zyra_garment_line_tv_board", LineTvBoard);
