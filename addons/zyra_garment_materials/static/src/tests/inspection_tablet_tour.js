/** @odoo-module **/
import { registry } from "@web/core/registry";

// Tablet inspection: open the roll queued for the test, tap a defect and a band, check the points, finish.
registry.category("web_tour.tours").add("zyra_fabric_inspection_tablet_tour", {
    url: "/odoo/action-zyra_garment_materials.action_fabric_inspection_tablet",
    steps: () => [
        {
            content: "Start the waiting roll",
            trigger: ".o_zyra_tab_start_roll:contains('RTOUR01')",
            run: "click",
        },
        {
            content: "Pick a defect",
            trigger: ".o_zyra_tab_defect:first",
            run: "click",
        },
        {
            content: "Tap the over 9 in band",
            trigger: ".o_zyra_tab_band[data-band='4']",
            run: "click",
        },
        {
            content: "Four penalty points shown",
            trigger: ".o_zyra_tab_points:contains('4')",
        },
        {
            content: "Finish the roll",
            trigger: ".o_zyra_tab_finish",
            run: "click",
        },
        {
            content: "Verdict shown",
            trigger: ".o_zyra_tab_verdict .o_zyra_tab_big:contains('Pass')",
        },
    ],
});
