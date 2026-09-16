import json
import azure.functions as func


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()

        errors = []

        # -------------------------
        # STEP 1: Validate INPUT
        # -------------------------
        request_body = data.get("body")
        queries = data.get("queries")

        if not request_body:
            errors.append("Missing 'body' in request")
        else:
            if not request_body.get("Method"):
                errors.append("Missing 'body.Method'")
            if not request_body.get("Uri"):
                errors.append("Missing 'body.Uri'")

        if not queries:
            errors.append("Missing 'queries'")
        else:
            if not queries.get("account"):
                errors.append("Missing 'queries.account'")

        # ✅ NEW: Validate CI_Build_status from Logic App
        ci_build_status = data.get("CI_Build_status")

        if not ci_build_status:
            errors.append("Missing 'CI_Build_status' (from Set Variable)")

        if errors:
            return func.HttpResponse(
                json.dumps(
                    {
                        "body": {
                            "status": "FAILED",
                            "stage": "INPUT_VALIDATION",
                            "errors": errors,
                        }
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        # -------------------------
        # STEP 2: Get Build Output
        # -------------------------
        build_output = data.get("checkbuildstatus_output")

        if not build_output:
            return func.HttpResponse(
                json.dumps(
                    {
                        "body": {
                            "status": "FAILED",
                            "stage": "BUILD_API_CALL",
                            "error": "Missing checkbuildstatus output",
                        }
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        build_body = build_output.get("body")

        if not build_body:
            return func.HttpResponse(
                json.dumps(
                    {
                        "body": {
                            "status": "FAILED",
                            "stage": "BUILD_OUTPUT_VALIDATION",
                            "error": "Missing 'body' in build response",
                        }
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        # -------------------------
        # STEP 3: REQUIRED FIELDS CHECK
        # -------------------------
        required_fields = [
            "id",
            "buildNumber",
            "sourceBranch",
            "definition",
            "_links",
        ]

        missing_fields = []

        for field in required_fields:
            if field not in build_body or build_body[field] in [None, ""]:
                missing_fields.append(field)

        # Nested validations
        if "_links" in build_body:
            if "web" not in build_body["_links"]:
                missing_fields.append("_links.web")

        if "definition" in build_body:
            if "id" not in build_body["definition"]:
                missing_fields.append("definition.id")
            if "name" not in build_body["definition"]:
                missing_fields.append("definition.name")

        if missing_fields:
            return func.HttpResponse(
                json.dumps(
                    {
                        "body": {
                            "status": "FAILED",
                            "stage": "PARSE_BUILD_JSON_VALIDATION",
                            "message": "Missing required fields in build response",
                            "missing_fields": missing_fields,
                        }
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        # -------------------------
        # STEP 4: BUILD STATUS CHECK (FROM LOGIC APP VARIABLE)
        # -------------------------
        # ✅ Use CI_Build_status instead of build_body
        if ci_build_status.lower() != "completed":
            return func.HttpResponse(
                json.dumps(
                    {
                        "body": {
                            "status": "IN_PROGRESS",
                            "stage": "BUILD_STATUS_CHECK",
                            "message": f"Build not completed yet. Current status: {ci_build_status}",
                            "build_id": build_body.get("id"),
                        }
                    }
                ),
                status_code=200,
                mimetype="application/json",
            )

        # -------------------------
        # STEP 5: FINAL SUCCESS
        # -------------------------
        return func.HttpResponse(
            json.dumps(
                {
                    "body": {
                        "status": "SUCCESS",
                        "stage": "BUILD_COMPLETED",
                        "message": "Build completed successfully",
                        "build_id": build_body.get("id"),
                        "build_status": ci_build_status,
                    }
                }
            ),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        return func.HttpResponse(
            json.dumps(
                {
                    "body": {
                        "status": "FAILED",
                        "stage": "EXCEPTION",
                        "error": str(e),
                    }
                }
            ),
            status_code=500,
            mimetype="application/json",
        )
    


"""import json
import azure.functions as func


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()

        errors = []

        # -------------------------
        # STEP 1: Validate INPUT
        # -------------------------
        body = data.get("body")
        queries = data.get("queries")

        if not body:
            errors.append("Missing 'body' in request")
        else:
            if not body.get("Method"):
                errors.append("Missing 'body.Method'")
            if not body.get("Uri"):
                errors.append("Missing 'body.Uri'")

        if not queries:
            errors.append("Missing 'queries'")
        else:
            if not queries.get("account"):
                errors.append("Missing 'queries.account'")

        if errors:
            return func.HttpResponse(
                json.dumps(
                    {
                        "status": "FAILED",
                        "stage": "INPUT_VALIDATION",
                        "errors": errors,
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        # -------------------------
        # STEP 2: Call Build API (checkbuildstatus output)
        # -------------------------
        build_output = data.get("checkbuildstatus_output")

        if not build_output:
            return func.HttpResponse(
                json.dumps(
                    {
                        "status": "FAILED",
                        "stage": "BUILD_API_CALL",
                        "error": "Missing checkbuildstatus output",
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        body = build_output.get("body")

        if not body:
            return func.HttpResponse(
                json.dumps(
                    {
                        "status": "FAILED",
                        "stage": "BUILD_OUTPUT_VALIDATION",
                        "error": "Missing 'body' in build response",
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        # -------------------------
        # STEP 3: REQUIRED FIELDS CHECK
        # -------------------------
        required_fields = [
            "id",
            "buildNumber",
            "status",
            "sourceBranch",
            "definition",
            "_links",
        ]

        missing_fields = []

        for field in required_fields:
            if field not in body or body[field] in [None, ""]:
                missing_fields.append(field)

        # Nested validations
        if "_links" in body:
            if "web" not in body["_links"]:
                missing_fields.append("_links.web")

        if "definition" in body:
            if "id" not in body["definition"]:
                missing_fields.append("definition.id")
            if "name" not in body["definition"]:
                missing_fields.append("definition.name")

        # -------------------------
        # STEP 4: FINAL RESPONSE
        # -------------------------
        if missing_fields:
            return func.HttpResponse(
                json.dumps(
                    {
                        "status": "FAILED",
                        "stage": "PARSE_BUILD_JSON_VALIDATION",
                        "message": "Missing required fields in build response",
                        "missing_fields": missing_fields,
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        return func.HttpResponse(
            json.dumps(
                {
                    "status": "SUCCESS",
                    "stage": "BUILD_VALIDATION",
                    "message": "All required fields are present",
                    "build_id": body.get("id"),
                    "build_status": body.get("status"),
                }
            ),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "FAILED",
                    "stage": "EXCEPTION",
                    "error": str(e),
                }
            ),
            status_code=500,
            mimetype="application/json",
        )
"""