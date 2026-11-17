/** @odoo-module **/
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { newUuid, scanQueue } from "./offline_queue";

/**
 * Scan station on the line (screen 4): scan the badge, then each coupon of the bundle ticket.
 * Every scan goes into an IndexedDB queue first and is sent with garment.scan.garment_sync_batch, so the
 * station keeps working when Wi-Fi drops and resending after reconnect cannot double-count.
 */
export class ScanStation extends Component {
    static template = "zyra_garment_sewing.ScanStation";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.input = useRef("input");
        const params = (this.props.action && this.props.action.params) || {};
        this.state = useState({
            lines: [], lineId: params.line_id || false, employee: null, stats: null,
            online: navigator.onLine, pending: 0, message: "", messageKind: "",
        });
        this._onOnline = () => {
            this.state.online = navigator.onLine;
            if (this.state.online) {
                this.flush();
            }
        };
        onWillStart(async () => {
            this.state.lines = await this.orm.call("garment.scan", "station_lines", []);
            if (!this.state.lineId && this.state.lines.length) {
                this.state.lineId = this.state.lines[0].id;
            }
            await this.refreshPending();
        });
        onMounted(() => {
            window.addEventListener("online", this._onOnline);
            window.addEventListener("offline", this._onOnline);
            this.focus();
            this.flush();
        });
        onWillUnmount(() => {
            window.removeEventListener("online", this._onOnline);
            window.removeEventListener("offline", this._onOnline);
        });
    }

    get lineName() {
        const line = this.state.lines.find((l) => l.id === Number(this.state.lineId));
        return line ? line.name : "";
    }

    focus() {
        if (this.input.el) {
            this.input.el.focus();
        }
    }

    async refreshPending() {
        try {
            this.state.pending = (await scanQueue.all()).length;
        } catch {
            this.state.pending = 0;
        }
    }

    async onKey(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        const code = ev.target.value.trim();
        ev.target.value = "";
        if (code) {
            await this.onCode(code);
        }
    }

    async onCode(code) {
        if (!code.startsWith("ZG1|")) {
            return this.badge(code);
        }
        if (!this.state.employee) {
            return this.say(_t("Scan your badge first."), "bad");
        }
        await scanQueue.add({
            uuid: newUuid(), payload: code, employee_id: this.state.employee.id,
            line_id: Number(this.state.lineId) || false, scanned_at: this.nowUtc(),
        });
        await this.refreshPending();
        await this.flush();
    }

    async badge(code) {
        try {
            this.state.employee = await this.orm.call("garment.scan", "station_badge", [code]);
            this.say("", "");
            await this.loadStats();
        } catch (err) {
            this.say(err.data ? err.data.message : String(err), "bad");
        }
    }

    nowUtc() {
        return new Date().toISOString().slice(0, 19).replace("T", " ");
    }

    async flush() {
        let items = [];
        try {
            items = await scanQueue.all();
        } catch {
            return;
        }
        if (!items.length || !navigator.onLine) {
            this.state.online = navigator.onLine;
            return;
        }
        try {
            const results = await this.orm.call("garment.scan", "garment_sync_batch", [items]);
            this.state.online = true;
            await scanQueue.remove(results.map((r) => r.uuid));
            const errors = results.filter((r) => r.status === "error");
            if (errors.length) {
                this.say(errors.map((e) => e.message).join(" · "), "bad");
            } else {
                this.say("", "");
            }
        } catch {
            this.state.online = false; // network gone: keep the queue
        }
        await this.refreshPending();
        await this.loadStats();
    }

    async loadStats() {
        if (!this.state.employee || !this.state.online) {
            return;
        }
        try {
            this.state.stats = await this.orm.call("garment.scan", "station_stats",
                [this.state.employee.id, Number(this.state.lineId) || false]);
        } catch {
            this.state.online = false;
        }
    }

    say(message, kind) {
        this.state.message = message;
        this.state.messageKind = kind;
    }

    money(value) {
        const s = this.state.stats;
        return `${s ? s.currency : ""}${(value || 0).toFixed(2)}`;
    }
}

registry.category("actions").add("zyra_garment_scan_station", ScanStation);
