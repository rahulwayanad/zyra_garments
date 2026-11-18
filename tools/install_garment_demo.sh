#!/usr/bin/env bash
# Create a database with the Zyra garment suite and ONLY the garment demo data (none of Odoo's own demo).
#
#   tools/install_garment_demo.sh <database> [--drop] [--tz <timezone>]
#
#   --drop        drop <database> (and its filestore) first if it already exists
#   --tz <zone>   timezone given to the admin user (default Asia/Kolkata). Set up front so the browser does not
#                 fill in a legacy alias such as Asia/Calcutta, which PostgreSQL without tzdata-legacy rejects
#                 in day/week/month groupings (the cockpit crashes on it).
#
# Environment:
#   ODOO_PATH   Odoo 18 source checkout (default: <repo>/odoo18, else <repo>/../odoo-18)
#   ODOO_CONF   Odoo config file        (default: $ODOO_PATH/odoo.conf)
#   ODOO_PYTHON Python with Odoo's deps  (default: $ODOO_PATH/venv/bin/python)
#
# Steps: [drop] -> create + install zyra_garment_suite without any demo -> tools/load_garment_demo.py -> admin tz.
# Never run this against production or the shared `garments` database.
set -euo pipefail

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-1}"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME=""
DROP=0
ADMIN_TZ="Asia/Kolkata"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --drop) DROP=1 ;;
        --tz) ADMIN_TZ="${2:?--tz needs a value}"; shift ;;
        -h|--help) usage 0 ;;
        -*) echo "Unknown option: $1" >&2; usage ;;
        *) [[ -z "$DB_NAME" ]] || usage; DB_NAME="$1" ;;
    esac
    shift
done
[[ -n "$DB_NAME" ]] || usage
if [[ "$DB_NAME" == "garments" ]]; then
    echo "Refusing: 'garments' is the shared database, never touched by this script." >&2
    exit 1
fi

if [[ -z "${ODOO_PATH:-}" ]]; then
    for candidate in "$REPO_DIR/odoo18" "$REPO_DIR/../odoo-18"; do
        if [[ -f "$candidate/odoo-bin" ]]; then ODOO_PATH="$(cd "$candidate" && pwd)"; break; fi
    done
fi
[[ -n "${ODOO_PATH:-}" && -f "$ODOO_PATH/odoo-bin" ]] || { echo "Odoo 18 not found: set ODOO_PATH." >&2; exit 1; }
ODOO_CONF="${ODOO_CONF:-$ODOO_PATH/odoo.conf}"
ODOO_PYTHON="${ODOO_PYTHON:-$ODOO_PATH/venv/bin/python}"
[[ -f "$ODOO_CONF" ]] || { echo "Config not found: $ODOO_CONF (set ODOO_CONF)." >&2; exit 1; }
[[ -x "$ODOO_PYTHON" ]] || { echo "Python not found: $ODOO_PYTHON (set ODOO_PYTHON)." >&2; exit 1; }
export ODOO_PATH

ADDONS_PATH="$ODOO_PATH/addons,$REPO_DIR/addons"
# --logfile= (empty): print to the terminal even when odoo.conf sets a logfile
ODOO_ARGS=(-c "$ODOO_CONF" --addons-path="$ADDONS_PATH" --logfile=)
odoo_bin() { (cd "$ODOO_PATH" && "$ODOO_PYTHON" odoo-bin "$@"); }

db_exists() {
    (cd "$ODOO_PATH" && "$ODOO_PYTHON" - "$ODOO_CONF" "$DB_NAME" <<'EOF'
import sys
import odoo
from odoo.service import db
odoo.tools.config.parse_config(["-c", sys.argv[1]])
sys.exit(0 if db.exp_db_exist(sys.argv[2]) else 1)
EOF
    )
}

if db_exists; then
    if [[ "$DROP" -eq 1 ]]; then
        echo "==> Dropping $DB_NAME (database + filestore)"
        odoo_bin db "${ODOO_ARGS[@]}" drop "$DB_NAME"
    else
        echo "Database $DB_NAME already exists. Pass --drop to recreate it." >&2
        exit 1
    fi
fi

echo "==> Creating $DB_NAME and installing zyra_garment_suite (no demo data)"
odoo_bin "${ODOO_ARGS[@]}" -d "$DB_NAME" -i zyra_garment_suite --without-demo=all --stop-after-init --no-http

echo "==> Loading the garment demo data only"
"$ODOO_PYTHON" "$REPO_DIR/tools/load_garment_demo.py" "${ODOO_ARGS[@]}" -d "$DB_NAME"

echo "==> Setting the admin timezone to $ADMIN_TZ"
odoo_bin shell "${ODOO_ARGS[@]}" -d "$DB_NAME" --no-http --log-level=warn <<EOF
admin = env.ref("base.user_admin")
admin.tz = "$ADMIN_TZ"
env.cr.commit()
EOF

echo "==> Done: $DB_NAME has the garment suite with garment demo data only (login admin / admin)."
