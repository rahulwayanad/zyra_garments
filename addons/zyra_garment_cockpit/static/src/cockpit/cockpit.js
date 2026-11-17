/** @odoo-module **/
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

const INK = "#1d1b2c";
const MUTED = "#6b6880";
const GRID = "#ece9f5";

// Draws the value above each bar (datasets flagged valueLabels) — Odoo does not bundle chartjs-plugin-datalabels.
const valueLabels = {
    id: "zyraValueLabels",
    afterDatasetsDraw(chart) {
        const { ctx } = chart;
        chart.data.datasets.forEach((ds, i) => {
            if (!ds.valueLabels) return;
            const meta = chart.getDatasetMeta(i);
            if (meta.hidden) return;
            ctx.save();
            ctx.fillStyle = INK;
            ctx.font = "500 11px sans-serif";
            ctx.textAlign = "center";
            meta.data.forEach((el, j) => {
                const v = ds.data[j];
                if (v === null || v === undefined) return;
                ctx.fillText(Number(v).toLocaleString(), el.x, el.y - 6);
            });
            ctx.restore();
        });
    },
};

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
        // draw once the DOM holds this data's canvases (a tab switch replaces them)
        const draw = () => {
            if (this.drawnFor !== this.state.data) {
                this.drawnFor = this.state.data;
                this.drawCharts();
            }
        };
        onMounted(draw);
        onPatched(draw);
        onWillUnmount(() => {
            clearInterval(this.timer);
            this.charts.forEach((c) => c.destroy());
        });
    }

    async load() {
        this.state.data = await this.orm.call("garment.cockpit", "get_cockpit", [this.state.key, this.state.filters]);
    }

    async reload() {
        await this.load(); // onPatched redraws the charts
    }

    async switchTo(key) {
        this.state.key = key;
        await this.reload();
    }

    async setFilter(name, value) {
        this.state.filters[name] = value;
        await this.reload();
    }

    async resetFilters() {
        this.state.filters = { days: 30, buyer_id: false, business_model: false };
        await this.reload();
    }

    toggleShift() {
        this.state.shift = this.state.shift === "day" ? "night" : "day";
    }

    fmtDate(iso) {
        if (!iso) return "";
        const [y, m, d] = iso.split("-");
        return `${d}/${m}/${y}`;
    }

    cellKind(cell) {
        if (cell === null || typeof cell !== "object") return "text";
        if ("pct" in cell) return "pct";
        if ("badge" in cell) return "badge";
        return "part";
    }

    fmt(tile) {
        if (tile.display) return tile.display;
        const v = tile.value;
        if (tile.fmt === "text") return v;
        if (tile.fmt === "pct") return `${Number(v || 0).toFixed(1)}%`;
        return (typeof v === "number" ? v : 0).toLocaleString();
    }

    tileClass(tile) {
        return "o_zyra_kpi" + (tile.state ? ` o_zyra_kpi_${tile.state}` : "") +
            (tile.fmt === "text" ? " o_zyra_kpi_text" : "") + (tile.model ? " o_zyra_kpi_link" : "");
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
        this.timer = setInterval(() => this.reload(), 60000);
    }

    drawCharts() {
        this.charts.forEach((c) => c.destroy());
        this.charts = [];
        if (!this.root.el) return;
        for (const panel of this.state.data.panels || []) {
            const canvas = this.root.el.querySelector(`canvas[data-panel="${panel.key}"]`);
            if (!canvas) continue;
            if (panel.type === "chart") this.charts.push(this.drawChart(canvas, panel));
            if (panel.type === "donut") this.charts.push(this.drawDonut(canvas, panel));
        }
    }

    drawChart(canvas, panel) {
        const line = panel.kind === "line";
        const datasets = panel.series.map((s) => ({
            label: s.label, data: s.values, backgroundColor: s.color, borderColor: s.color,
            borderWidth: line ? 2 : 0, borderRadius: line ? 0 : 3, cubicInterpolationMode: "monotone", pointRadius: 0,
            spanGaps: true, valueLabels: panel.value_labels, maxBarThickness: 64,
        }));
        if (panel.ref !== null && panel.ref !== undefined) {
            datasets.push({ type: "line", label: "", data: panel.labels.map(() => panel.ref), borderColor: INK,
                borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, fill: false, isRef: true });
        }
        const axis = { grid: { color: GRID }, border: { display: false }, ticks: { color: MUTED } };
        return new window.Chart(canvas, {
            type: panel.kind,
            data: { labels: panel.labels, datasets },
            plugins: [valueLabels],
            options: {
                responsive: true, maintainAspectRatio: false,
                layout: { padding: { top: panel.value_labels ? 18 : 0 } },
                scales: {
                    x: { ...axis, stacked: panel.stacked, grid: { display: false } },
                    y: { ...axis, stacked: panel.stacked, beginAtZero: true },
                },
                plugins: {
                    legend: {
                        display: panel.legend, position: "top", align: "end",
                        labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 6, boxHeight: 6, color: MUTED,
                            filter: (item, data) => !data.datasets[item.datasetIndex].isRef },
                    },
                    tooltip: { filter: (item) => !item.dataset.isRef },
                },
            },
        });
    }

    drawDonut(canvas, panel) {
        return new window.Chart(canvas, {
            type: "doughnut",
            data: {
                labels: panel.segments.map((s) => s.label),
                datasets: [{ data: panel.segments.map((s) => s.value),
                    backgroundColor: panel.segments.map((s) => s.color), borderWidth: 0 }],
            },
            options: { responsive: true, maintainAspectRatio: false, cutout: "72%",
                plugins: { legend: { display: false } } },
        });
    }
}

registry.category("actions").add("zyra_garment_cockpit", GarmentCockpit);
