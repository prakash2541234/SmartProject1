import json
import logging

logging.basicConfig(level=logging.INFO)

def storelogs():
    logging.info("Program started. Waiting for JSON input...")
    print("Paste JSON payload (press ENTER twice to finish):")

    lines = []
    while True:
        line = input()
        if line.strip() == "":
            break
        lines.append(line)

    user_input = "\n".join(lines)

    try:
        data = json.loads(user_input)
    except json.JSONDecodeError as e:
        logging.warning("Invalid JSON format")
        print(json.dumps({
            "message": "Invalid JSON format",
            "error": str(e)
        }, indent=4))
        return

    if data:
        logging.info(f"Payload received: {data}")

        required_fields = [
            "u_catalog_task_sysid",
            "u_ritm_number",
            "u_state",
            "u_result"
        ]

        missing_fields = [
            field for field in required_fields
            if field not in data or data[field] is None
        ]

        if missing_fields:
            print(json.dumps({
                "message": "Payload is missing required fields",
                "missing_fields": missing_fields
            }, indent=4))
            return

        print(json.dumps({
            "message": "Payload received successfully",
            "data": data
        }, indent=4))

    else:
        print(json.dumps({
            "message": "Payload not received"
        }, indent=4))


if __name__ == "__main__":
    storelogs()
