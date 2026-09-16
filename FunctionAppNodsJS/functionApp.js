const { app } = require('@azure/functions');

let PROCESS_TRACKER = {};

// ==========================================
// ✅ COMMON HELPERS
// ==========================================
function jsonResponse(status, body) {
    return {
        status: status,
        jsonBody: body
    };
}

// ==========================================
// ✅ 1. STORE LOGS
// ==========================================
app.http('storelogs', {
    methods: ['POST'],
    authLevel: 'function',
    handler: async (req, context) => {
        context.log("Processing storelogs request...");

        try {
            const data = await req.json();

            if (!data) {
                return jsonResponse(400, {
                    message: "Payload not received"
                });
            }

            const requiredFields = [
                "u_catalog_task_sysid",
                "u_ritm_number",
                "u_state",
                "u_result"
            ];

            let missingFields = [];

            for (let field of requiredFields) {
                if (!(field in data) || data[field] === null) {
                    missingFields.push(field);
                }
            }

            if (missingFields.length > 0) {
                return jsonResponse(400, {
                    message: "Payload is missing required fields",
                    missing_fields: missingFields
                });
            }

            return jsonResponse(200, {
                message: "Payload received successfully",
                data: data
            });

        } catch (err) {
            context.log.error(err);
            return jsonResponse(500, { error: err.message });
        }
    }
});

// ==========================================
// ✅ 2. WORKFLOW TRACKER
// ==========================================
app.http('workflowTracker', {
    methods: ['POST'],
    authLevel: 'function',
    handler: async (req, context) => {
        context.log("Processing workflow tracking request...");

        try {
            const data = await req.json();

            if (!data) {
                return jsonResponse(400, { message: "Empty payload" });
            }

            const task_id = data.u_catalog_task_sysid;
            const ritm = data.u_ritm_number;

            if (!task_id || !ritm) {
                return jsonResponse(400, {
                    message: "Missing required identifiers"
                });
            }

            if (!PROCESS_TRACKER[task_id]) {
                PROCESS_TRACKER[task_id] = {
                    subscription: false,
                    role: false,
                    service_principal: false,
                    key_vault: false,
                    backup: false
                };
            }

            const tracker = PROCESS_TRACKER[task_id];

            // ✅ Combined payload
            if (
                data.u_SubName ||
                data.RollAssign ||
                data.SP_name ||
                data.KV_name ||
                data.BackUP
            ) {
                if (data.u_SubName) tracker.subscription = true;
                if (data.RollAssign) tracker.role = true;
                if (data.SP_name) tracker.service_principal = true;
                if (data.KV_name) tracker.key_vault = true;
                if (data.BackUP) tracker.backup = true;

                context.log("Processed combined payload");
            }
            // ✅ Single step
            else {
                let step = null;

                if (data.u_SubName) step = "subscription";
                else if (data.RollAssign) step = "role";
                else if (data.SP_name) step = "service_principal";
                else if (data.KV_name) step = "key_vault";
                else if (data.BackUP) step = "backup";

                if (step) {
                    tracker[step] = true;
                } else {
                    return jsonResponse(400, {
                        message: "Unknown payload type"
                    });
                }
            }

            const allDone = Object.values(tracker).every(v => v === true);

            return jsonResponse(200, {
                message: allDone ? "All steps completed" : "Workflow in progress",
                status: allDone ? "completed" : "in_progress",
                tracker
            });

        } catch (err) {
            context.log.error(err);
            return jsonResponse(500, { error: err.message });
        }
    }
});

// ==========================================
// ✅ 3. SubCheck
// ==========================================
app.http('SubCheck', {
    methods: ['POST'],
    authLevel: 'function',
    handler: async (req, context) => {
        context.log("Processing SubCheck request...");

        try {
            const data = await req.json();

            if (!data || !data.u_SubName || typeof data.u_SubName !== "string" || !data.u_SubName.trim()) {
                return jsonResponse(400, {
                    message: "Invalid value for 'u_SubName'"
                });
            }

            return jsonResponse(200, {
                message: "Payload received successfully",
                data
            });

        } catch (err) {
            return jsonResponse(500, { error: err.message });
        }
    }
});

// ==========================================
// ✅ 4. RollCheck
// ==========================================
app.http('RollCheck', {
    methods: ['POST'],
    authLevel: 'function',
    handler: async (req, context) => {
        context.log("Processing RollCheck request...");

        try {
            const data = await req.json();

            if (!data || !data.u_Roll || typeof data.u_Roll !== "string" || !data.u_Roll.trim()) {
                return jsonResponse(400, {
                    message: "Invalid value for 'u_Roll'"
                });
            }

            return jsonResponse(200, {
                message: "Payload received successfully",
                data
            });

        } catch (err) {
            return jsonResponse(500, { error: err.message });
        }
    }
});