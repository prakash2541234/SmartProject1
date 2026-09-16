import json
import azure.functions as func


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()

        errors = []
        warnings = []

        # =====================================================
        # STEP 1 : VALIDATE GET RELEASE STATUS INPUT
        # =====================================================

        get_release_status_input = data.get(
            "get_release_status_input"
        )

        if not get_release_status_input:

            errors.append(
                "Get ReleaseStatus failed to receive input payload"
            )

        else:

            input_body = get_release_status_input.get(
                "body",
                {}
            )

            queries = input_body.get(
                "queries",
                {}
            )

            request_body = input_body.get(
                "body",
                {}
            )

            method = get_release_status_input.get(
                "method"
            )

            missing_fields = []

            if not queries.get("account"):
                missing_fields.append(
                    "body.queries.account"
                )

            if not request_body.get("Uri"):
                missing_fields.append(
                    "body.body.Uri"
                )

            if not request_body.get("Method"):
                missing_fields.append(
                    "body.body.Method"
                )

            if not method:
                missing_fields.append(
                    "method"
                )

            if missing_fields:
                errors.append(
                    f"Get ReleaseStatus input missing payload fields: {missing_fields}"
                )

        # =====================================================
        # STEP 2 : VALIDATE GET RELEASE STATUS OUTPUT
        # =====================================================

        get_release_status_output = data.get(
            "get_release_status_output"
        )

        release_body = {}

        if not get_release_status_output:

            errors.append(
                "Get ReleaseStatus failed to send output payload"
            )

        else:

            status_code = (
                get_release_status_output.get(
                    "statusCode"
                )
            )

            if status_code != 200:

                errors.append(
                    f"Get ReleaseStatus API returned statusCode {status_code}"
                )

            else:

                wrapper_body = (
                    get_release_status_output.get(
                        "body",
                        {}
                    )
                )

                release_body = (
                    wrapper_body.get(
                        "body",
                        {}
                    )
                )

                missing_fields = []

                if not release_body.get("id"):
                    missing_fields.append(
                        "body.body.id"
                    )

                if not release_body.get("name"):
                    missing_fields.append(
                        "body.body.name"
                    )

                if not release_body.get("status"):
                    missing_fields.append(
                        "body.body.status"
                    )

                environments = release_body.get(
                    "environments",
                    []
                )

                if not environments:

                    missing_fields.append(
                        "body.body.environments"
                    )

                else:

                    env = environments[0]

                    if not env.get("id"):
                        missing_fields.append(
                            "body.body.environments[0].id"
                        )

                    if not env.get("status"):
                        missing_fields.append(
                            "body.body.environments[0].status"
                        )

                if missing_fields:

                    errors.append(
                        f"Get ReleaseStatus output missing payload fields: {missing_fields}"
                    )

        # =====================================================
        # STEP 3 : VALIDATE PARSE JSON OUTPUT
        # =====================================================

        parse_json_output = data.get(
            "parse_json_output"
        )

        if not parse_json_output:

            errors.append(
                "Parse JSON 1 failed to produce output payload"
            )

        else:

            body = parse_json_output.get(
                "body",
                {}
            )

            missing_fields = []

            if not body.get("status"):

                missing_fields.append(
                    "body.status"
                )

            environments = body.get(
                "environments",
                []
            )

            if not environments:

                missing_fields.append(
                    "body.environments"
                )

            else:

                env_status = environments[0].get(
                    "status"
                )

                if not env_status:

                    missing_fields.append(
                        "body.environments[0].status"
                    )

            if missing_fields:

                errors.append(
                    f"Parse JSON output missing payload fields: {missing_fields}"
                )

        # =====================================================
        # STEP 4 : VALIDATE SET RELEASE STATUS
        # =====================================================

        set_release_status_output = data.get(
            "set_releasestatus_output"
        )

        final_status = "UNKNOWN"

        if not set_release_status_output:

            errors.append(
                "Set releasestatus action failed to produce output payload"
            )

        else:

            final_status = (
                set_release_status_output.get(
                    "releasestatus"
                )
            )

            if not final_status:

                errors.append(
                    "Set releasestatus output missing field: releasestatus"
                )

        # =====================================================
        # FINAL RESULT
        # =====================================================

        if errors:

            return func.HttpResponse(
                json.dumps(
                    {
                        "body": {
                            "status": "FAILED",
                            "stage": "VALIDATION",
                            "errors": errors,
                            "warnings": warnings
                        }
                    }
                ),
                status_code=400,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps(
                {
                    "body": {
                        "status": "SUCCESS",
                        "stage": "VALIDATION_COMPLETE",
                        "release_id": release_body.get(
                            "id"
                        ),
                        "release_name": release_body.get(
                            "name"
                        ),
                        "release_status": final_status,
                        "environment_status": release_body.get(
                            "environments",
                            [{}]
                        )[0].get(
                            "status"
                        ),
                        "message": (
                            "Get ReleaseStatus, Parse JSON and "
                            "Set releasestatus validated successfully"
                        ),
                        "warnings": warnings
                    }
                }
            ),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:

        return func.HttpResponse(
            json.dumps(
                {
                    "body": {
                        "status": "FAILED",
                        "stage": "EXCEPTION",
                        "error": str(e)
                    }
                }
            ),
            status_code=500,
            mimetype="application/json"
        )