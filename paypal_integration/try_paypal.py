"""
Quick check that your Sandbox credentials work (run from the project root):

    python -m paypal_integration.try_paypal

It gets a token and creates a $1.00 Sandbox order, then prints a link.
Open the link, log in with your Sandbox PERSONAL account (sb-...@personal.example.com),
approve, then capture it with:

    python -m paypal_integration.try_paypal --capture <ORDER_ID>

Never prints your secret or token.
"""

import argparse
import sys

from paypal_integration.client import PayPalClient
from paypal_integration.errors import ModuleError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test the PayPal Sandbox connection.")
    parser.add_argument("--capture", metavar="ORDER_ID", help="capture an order you already approved")
    parser.add_argument("--amount", default="1.00", help="order amount in USD (default 1.00)")
    args = parser.parse_args(argv)

    client = PayPalClient()
    try:
        client.get_access_token()
        print(f"OK  Connected to {client.api_base} (token received)")
        if args.capture:
            result = client.capture_order(args.capture)
            print(f"OK  Captured order {result['id']}: {result['status']}, "
                  f"{result['amount']} {result['currency']}, capture ID {result['capture_id']}")
            return 0
        order = client.create_order(args.amount)
        print(f"OK  Created order {order['id']} ({order['status']})")
        print(f"    1. Open: {order['approve_url']}")
        print("    2. Log in with your Sandbox PERSONAL account and approve")
        print(f"    3. Run:  python -m paypal_integration.try_paypal --capture {order['id']}")
        return 0
    except ModuleError as error:
        print(f"ERROR {error.code}: {error.message}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
