/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Line planning board (screen 3): orders as bars on lines, load against capacity; drag a bar to another
 * line or week (drop on a week column of a line row). */
export class LinePlanningBoard extends Component {
    static template = "zyra_garment_sewing.LinePlanningBoard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: null, dragId: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("garment.line.plan", "garment_board", [], { weeks: 8 });
    }

    async planOrders() {
        await this.orm.call("garment.line.plan", "garment_plan_orders", []);
        await this.load();
    }

    loadClass(load) {
        return load > 100 ? "o_zyra_pb_bad" : load >= 95 ? "o_zyra_pb_warn" : "o_zyra_pb_good";
    }

    barClass(bar) {
        return bar.late ? "o_zyra_pb_bar_late" : bar.clash ? "o_zyra_pb_bar_clash" : `o_zyra_pb_bar_c${bar.id % 3}`;
    }

    onDragStart(bar) {
        this.state.dragId = bar.id;
    }

    async onDrop(line, week) {
        if (!this.state.dragId) {
            return;
        }
        const id = this.state.dragId;
        this.state.dragId = false;
        try {
            await this.orm.call("garment.line.plan", "garment_move", [[id], line.id, week.date]);
        } catch (err) {
            this.notification.add(err.data ? err.data.message : String(err), { type: "danger" });
        }
        await this.load();
    }

    openBar(bar) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "garment.line.plan", res_id: bar.id,
                               views: [[false, "form"]], target: "new" });
    }
}

registry.category("actions").add("zyra_garment_line_planning_board", LinePlanningBoard);
