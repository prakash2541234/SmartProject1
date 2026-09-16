import json
import azure.functions as func


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()

        errors = []
        warnings = []

        # =====================================================
        # STEP 1: VALIDATE CREATE RELEASE INPUT
        # =====================================================
        create_release_input = data.get("create_release_input")

        if not create_release_input:
            warnings.append(
                "create_release_input not provided by Logic App"
            )
            
        else:
            request_body = create_release_input.get("body", {})

            if (
                isinstance(request_body, dict)
                and "queries" in request_body
            ):
                body = request_body.get("body", {})
                queries = request_body.get("queries", {})
                path = request_body.get("path")
            else:
                body = create_release_input.get("body", {})
                queries = create_release_input.get("queries", {})
                path = create_release_input.get("path")

            if not body.get("Description"):
                errors.append("Missing body.Description")

            if body.get("IsDraft") is None:
                errors.append("Missing body.IsDraft")

            if not body.get("Reason"):
                errors.append("Missing body.Reason")

            if not queries.get("account"):
                errors.append("Missing queries.account")

            if not queries.get("releaseDefId"):
                errors.append("Missing queries.releaseDefId")

            if not path:
                errors.append("Missing path")

        # =====================================================
        # STEP 2: VALIDATE CREATE RELEASE OUTPUT
        # =====================================================
        create_release_output = data.get("create_release_output")

        release_body = {}

        if not create_release_output:
            errors.append(
                "Create Release action did not run or failed"
            )

        else:
            status_code = create_release_output.get(
                "statusCode"
            )

            if status_code != 200:
                errors.append(
                    f"Create Release failed with statusCode {status_code}"
                )

            else:
                outer_body = create_release_output.get(
                    "body", {}
                )

                # Custom failure response
                if (
                    isinstance(outer_body, dict)
                    and outer_body.get("status")
                    == "FAILED"
                ):
                    errors.append(
                        "Create Release returned FAILED response"
                    )

                    if outer_body.get("missing_fields"):
                        errors.extend(
                            outer_body.get(
                                "missing_fields", []
                            )
                        )

                    if outer_body.get("details"):
                        errors.extend(
                            outer_body.get("details", [])
                        )

                else:
                    # Handle nested body.body
                    release_body = outer_body.get(
                        "body",
                        outer_body
                    )

                    release_id = (
                        release_body.get("Id")
                        or release_body.get("id")
                    )

                    release_status = (
                        release_body.get("Status")
                        or release_body.get("status")
                    )

                    environments = (
                        release_body.get("Environments")
                        or release_body.get("environments")
                        or []
                    )

                    if not release_id:
                        errors.append(
                            "Missing Release Id"
                        )

                    if not release_status:
                        errors.append(
                            "Missing Release Status"
                        )

                    if not environments:
                        errors.append(
                            "Missing Environments in release output"
                        )
                    else:
                        env = environments[0]

                        env_id = (
                            env.get("Id")
                            or env.get("id")
                        )

                        env_status = (
                            env.get("Status")
                            or env.get("status")
                        )

                        if not env_id:
                            errors.append(
                                "Missing Environment Id"
                            )

                        if not env_status:
                            errors.append(
                                "Missing Environment Status"
                            )

        # =====================================================
        # STEP 3: VALIDATE UNTIL LOOP OUTPUT
        # =====================================================

        until_output = (
            data.get("until_output")
            or data.get("until_ouput")
        )

        final_status = "UNKNOWN"

        if not until_output:
            warnings.append(
                "Until condition did not run or was skipped"
            )

        else:

            # Current payload format:
            # {
            #   "final_release_status": "succeeded"
            # }

            if "final_release_status" in until_output:

                final_status = (
                    until_output.get(
                        "final_release_status",
                        "UNKNOWN"
                    )
                )

            else:

                status_code = until_output.get(
                    "statusCode"
                )

                if (
                    status_code
                    and status_code != 200
                ):
                    errors.append(
                        f"Until loop API failed with statusCode {status_code}"
                    )

                body = until_output.get("body")

                if not body:
                    warnings.append(
                        "Until loop body not supplied"
                    )

                else:

                    environments = (
                        body.get("Environments")
                        or body.get("environments")
                        or []
                    )

                    if environments:

                        env_status = (
                            environments[0].get(
                                "Status"
                            )
                            or environments[0].get(
                                "status"
                            )
                        )

                        if env_status:
                            final_status = env_status
                        else:
                            errors.append(
                                "Missing Environment Status in Until loop"
                            )

                    else:
                        errors.append(
                            "No Environments found in Until loop output"
                        )

        # =====================================================
        # STEP 4: FINAL RESULT
        # =====================================================

        if errors:
            return func.HttpResponse(
                json.dumps(
                    {
                        "body": {
                            "status": "FAILED",
                            "stage": "VALIDATION",
                            "errors": errors,
                            "warnings": warnings,
                        }
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        return func.HttpResponse(
            json.dumps(
                {
                    "body": {
                        "status": "SUCCESS",
                        "stage": "MONITORING_COMPLETE",
                        "release_status": final_status,
                        "release_id": (
                            release_body.get("Id")
                            or release_body.get("id")
                        ),
                        "message": "Release pipeline monitored successfully",
                        "warnings": warnings,
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