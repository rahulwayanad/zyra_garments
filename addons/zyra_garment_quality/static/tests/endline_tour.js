import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("zyra_garment_endline_tour", {
    steps: () => [
        {
            content: "Pick the test line",
            trigger: ".o_zyra_el_line_btn:contains('QA Tour Line')",
            run: "click",
        },
        {
            content: "Tablet open on the line",
            trigger: ".o_zyra_el_title:contains('QA Tour Line')",
        },
        {
            content: "Count a good piece",
            trigger: ".o_zyra_el_good",
            run: "click",
        },
        {
            content: "One piece this hour",
            trigger: ".o_zyra_el_hour_checked:contains('1')",
        },
        {
            content: "Tap where",
            trigger: ".o_zyra_el_btn[data-position='left_sleeve']",
            run: "click",
        },
        {
            content: "Tap what",
            trigger: ".o_zyra_el_btn[data-defect]:first",
            run: "click",
        },
        {
            content: "Record the defect",
            trigger: ".o_zyra_el_record:enabled",
            run: "click",
        },
        {
            content: "Two pieces this hour",
            trigger: ".o_zyra_el_hour_checked:contains('2')",
        },
    ],
});
