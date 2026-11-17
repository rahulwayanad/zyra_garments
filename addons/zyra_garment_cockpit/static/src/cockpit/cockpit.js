/** @odoo-module **/
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

export class GarmentCockpit extends Component {
    static template = "zyra_garment_cockpit.Cockpit";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.root = useRef("root");
        const params = (this.props.action && this.props.action.params) || {};
        this.state = useState({ key: params.cockpit || "pulse", data: null, live: false, shift: "day",
            filters: { days: 30, buyer_id: false, business_model: false } });
        this.charts = [];
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        onMounted(() => this.drawCharts());
        onWillUnmount(() => {
            clearInterval(this.timer);
            this.charts.forEach((c) => c.destroy());
        });
    }

    async load() {
        this.state.data = await this.orm.call("garment.cockpit", "get_cockpit", [this.state.key, this.state.filters]);
    }

    async switchTo(key) {
        this.state.key = key;
        await this.load();
        this.drawCharts();
    }

    async setFilter(name, value) {
        this.state.filters[name] = value;
        await this.load();
        this.drawCharts();
    }

    async resetFilters() {
        this.state.filters = { days: 30, buyer_id: false, business_model: false };
        await this.load();
        this.drawCharts();
    }

    toggleShift() {
        this.state.shift = this.state.shift === "day" ? "night" : "day";
    }

    fmt(tile) {
        const v = tile.value;
        if (tile.fmt === "text") return v;
        if (tile.fmt === "pct") return `${v}%`;
        if (tile.fmt === "money") return Math.round(v).toLocaleString();
        return (typeof v === "number" ? v : 0).toLocaleString();
    }

    tileClass(tile) {
        return "o_zyra_kpi" + (tile.state ? ` o_zyra_kpi_${tile.state}` : "") + (tile.fmt === "text" ? " o_zyra_kpi_text" : "");
    }

    openTile(tile) {
        if (!tile.model) return;
        this.action.doAction({
            type: "ir.actions.act_window", name: tile.label, res_model: tile.model, domain: tile.domain,
            views: [[false, "list"], [false, "form"]], target: "current",
        });
    }

    openRecord(model, id) {
        if (model && id) {
            this.action.doAction({ type: "ir.actions.act_window", res_model: model, res_id: id,
                views: [[false, "form"]], target: "current" });
        }
    }

    present() {
        const el = this.root.el;
        if (el && el.requestFullscreen) el.requestFullscreen();
        this.state.live = true;
        clearInterval(this.timer);
        this.timer = setInterval(async () => { await this.load(); this.drawCharts(); }, 60000);
    }

    drawCharts() {
        this.charts.forEach((c) => c.destroy());
        this.charts = [];
        const purple = "#6d4ae8";
        for (const chart of this.state.data.charts || []) {
            const canvas = this.root.el && this.root.el.querySelector(`canvas[data-chart="${chart.key}"]`);
            if (!canvas) continue;
            const line = chart.type === "line";
            const datasets = [];
            if (chart.targets) {
                datasets.push({ label: chart.target_label || "Target", data: chart.targets,
                    backgroundColor: line ? "#d97706" : "#c9bff7", borderColor: line ? "#d97706" : "#c9bff7",
                    tension: 0.3, pointRadius: 0 });
            }
            const main = chart.key === "lines" ? "#10a37f" : purple;
            datasets.push({ label: chart.label || chart.title, data: chart.values, backgroundColor: main,
                borderColor: main, tension: 0.3, pointRadius: 0 });
            this.charts.push(new window.Chart(canvas, {
                type: chart.type, data: { labels: chart.labels, datasets },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, position: "top", align: "end" } } },
            }));
        }
    }
}

registry.category("actions").add("zyra_garment_cockpit", GarmentCockpit);
