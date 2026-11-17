/** @odoo-module **/
// Tiny IndexedDB queue for scans taken while the network is down. Keyed by the scan's uuid, so a scan is
// stored once and removed only after the server has answered for it (ok / duplicate / error).
const DB_NAME = "zyra_garment_scan_station";
const STORE = "queue";

function openDb() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, 1);
        req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "uuid" });
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function run(mode, fn) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const result = fn(tx.objectStore(STORE));
        tx.oncomplete = () => resolve(result && "result" in result ? result.result : undefined);
        tx.onerror = () => reject(tx.error);
    });
}

export const scanQueue = {
    add: (item) => run("readwrite", (s) => s.put(item)),
    all: () => run("readonly", (s) => s.getAll()),
    remove: (uuids) => run("readwrite", (s) => uuids.forEach((u) => s.delete(u))),
};

export function newUuid() {
    if (window.crypto && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
