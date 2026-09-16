import azure.functions as func

from subscription_handler import handle_subscription_request


def main(req: func.HttpRequest) -> func.HttpResponse:
    return handle_subscription_request(req)
