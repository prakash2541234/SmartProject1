import json
import azure.functions as func

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()

        result = {
            "subscription_name": None,
            "createSub_input": None,
            "parse_output": None,
            "http1_checked": False,
            "errors": []
        }

        sub_name = body.get("create_payload_response", {}).get("subscription_name")

        if sub_name:
            result["subscription_name"] = {
                "status" : "OK",
                "value": sub_name
            }

            # ✅ STOP here (no further checks needed)
            return func.HttpResponse(
                json.dumps({
                    "message": "Subscription name exists. No validation needed.",
                    "result": result
                }),
                status_code=200
            )

        # ❌ If subscription_name missing → continue validation
        result["subscription_name"] = {
            "status": "MISSING",
            "value": None
        }
        result["errors"].append("subscription_name missing")

        # Step 2: Check createSub workflow input
        create_sub = body.get("createsub_workflow_input")

        if not create_sub:
            result["createSub_input"] = {
                "status": "MISSING",
                "value": None
            }
            result["errors"].append("createSub workflow input missing")

            # Step 3: Check parsed payload
            parsed = body.get("parsed_payload")

            if not parsed or not parsed.get("subscription_name"):
                result["parse_output"] = {
                    "status": "MISSING",
                    "value": None
                }
                result["errors"].append("parsed_payload invalid")

                # Step 4: Final fallback → http1 check
                http1 = body.get("trigger_payload")

                if not http1:
                    result["http1_checked"] = {
                        "status": "MISSING",
                        "value": None
                    }
                    result["errors"].append("http1 payload missing")
                else:
                    result["http1_checked"] = {
                        "status": "OK",
                        "value": http1
                    }

            else:
                result["parse_output"] = {
                    "status": "OK",
                    "value": parsed.get("subscription_name")
                }

        else:
            result["createSub_input"] = {
                "status": "OK",
                "value": create_sub
            }

        return func.HttpResponse(
            json.dumps(result),
            status_code=200
        )

    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500
        )