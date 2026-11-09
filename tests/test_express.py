import json  
from pathlib import Path
import subprocess  
import sys
from tempfile import TemporaryDirectory  
import unittest

from supplydesk.service import OrderService  


def item(product_id, quantity):  # Define the item helper.
    return {"product_id": product_id, "quantity": quantity}


class ExpressTests(unittest.TestCase):  # Group the express delivery checks.
    def setUp(self):
        # Give every test a new and fresh save file so that the tests do not change real orders.
        directory = TemporaryDirectory()  # Create an  folder for this test.
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state.json"  # Choose the test save file.
        self.service = OrderService(self.path)

    def command(self, *args, inputs=None):  # Define the command helper.
        return subprocess.run(
            [sys.executable, "-m", "supplydesk", "--data", str(self.path), *args],  # Use this Python interpreter and pass the temporary save path.
            input=inputs, text=True, capture_output=True, timeout=10,
        )  # End this list, mapping, or function call.

    def stock(self, product_id):  # Define the stock helper.
        return next(p["stock"] for p in self.service.catalog()
                    if p["product_id"] == product_id)  # Match the product by its own ID.

    def test_express_examples(self):  # Test express examples.
        # Use the three examples from the change request as expected totals.
        cases = [  # List the inputs and expected results to check.
            ("regular", "notebook", 2, 1000, 0, 2200),
            ("student", "hoodie", 2, 8000, 800, 8400),  # Set up this pricing example and its expected result.
            ("regular", "hoodie", 3, 12000, 0, 13200),
        ]  # End this list, mapping, or function call.
        for customer, product, quantity, subtotal, discount, total in cases:
            with self.subTest(customer=customer, product=product, quantity=quantity):  # Label each case by itself in the test output.
                quote = self.service.quote(customer, [item(product, quantity)], "express")
                self.assertEqual(quote["fulfillment"], "express")  # Check which fulfillment type was used.
                self.assertEqual(quote["subtotal_cents"], subtotal)
                self.assertEqual(quote["discount_cents"], discount)  # Check the merchandise discount.
                self.assertEqual(quote["delivery_cents"], 1200)
                self.assertEqual(quote["total_cents"], total)  # Check the final amount in cents.
        self.assertFalse(self.path.exists())

    def test_student_eligibility_matches_existing_pickup(self):  # test the students eligibility matches existing pickup.
        # do a compariosn with the student discount with pickup on both sides of the threshold.
        for quantity in (9, 10, 11):  # Run the check for each case in the list.
            with self.subTest(quantity=quantity):
                items = [item("notebook", quantity)]  # Build the item list for this case.
                pickup = self.service.quote("student", items)
                express = self.service.quote("student", items, "express")  # get a quote using these customer and delivery inputs.
                self.assertEqual(express["discount_cents"], pickup["discount_cents"])
                self.assertEqual(express["total_cents"], pickup["total_cents"] + 1200)  # see the final amount in cents.

    def test_standard_threshold_uses_discounted_subtotal(self):  # Test standard threshold using the discounted subtotal.
        # Check below and at the free standard delivery threshold, including a discount.
        cases = [  # List the inputs and expected results to check.
            ("regular", [item("notebook", 19)], 600),
            ("regular", [item("notebook", 20)], 0),  # Set up this pricing example and its expected result.
            ("regular", [item("hoodie", 3)], 0),
            ("student", [item("notebook", 20)], 600),  # Set up this pricing example and its expected result.
        ]
        for customer, items, fee in cases:  # Run the check for every single case in the list.
            with self.subTest(customer=customer, items=items):
                standard = self.service.quote(customer, items, "delivery")  # Request a quote using these customer and delivery inputs.
                self.assertEqual(standard["delivery_cents"], fee)
                self.assertEqual(self.service.quote(customer, items)["delivery_cents"], 0)  # Check the delivery charge.
                self.assertEqual(
                    self.service.quote(customer, items, "express")["delivery_cents"], 1200  # Read the express fee for the same items.
                )

    def test_order_snapshot_stock_history_and_numbering(self):  
        # Follow the process of an express order from quote to placement, reopening, and cancellation.
        items = [item("hoodie", 2), item("notebook", 1)]  # Build the item list for this case.
        quote = self.service.quote("student", items, "express")
        order = self.service.place_order("student", items, "express")  # Place an order in the test save file.
        expected = {"order_id": "ORD-0001", "status": "placed", **quote}
        self.assertEqual(order, expected)  # Compare the complete order with what we are expected in the record.
        self.assertEqual((self.stock("hoodie"), self.stock("notebook")), (3, 19))
        self.assertEqual(self.service.get_order("ORD-0001"), expected)  # Compare the retrieved record with the expected order.

        reopened = OrderService(self.path)  # Create a new service pointed at the same save file.
        self.assertEqual(reopened.list_orders(), [expected])
        self.assertEqual(reopened.get_order("ORD-0001"), expected)  # Compare the records we got with the expected order.
        cancelled = {**expected, "status": "cancelled"}
        self.assertEqual(reopened.cancel_order("ORD-0001"), cancelled)  # Check the order returned after cancellation.
        self.assertEqual((self.stock("hoodie"), self.stock("notebook")), (5, 20))
        second = reopened.place_order("regular", [item("notebook", 1)])  # Place an order in the test save file.
        self.assertEqual(second["order_id"], "ORD-0002")
        self.assertEqual(second["fulfillment"], "pickup")  # Check which fulfillment was used.
        self.assertEqual(OrderService(self.path).list_orders(), [cancelled, second])

    def test_invalid_fulfillment_and_stock_preserve_state(self):  # Test any invalid fulfillment and stock preserve state.
        # Compare the save file before and after the rejected requests.
        self.service.place_order("regular", [item("hoodie", 1)])  # Complete this step in the order or test flow.
        before = self.path.read_bytes()
        for operation in (self.service.quote, self.service.place_order):  # Run the check for each case in the list.
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "Fulfillment"):  # Require the expected error and check its message.
                    operation("regular", [item("notebook", 1)], "overnight")
                with self.assertRaisesRegex(ValueError, "Not enough stock"):  # Require the expected error and check its message.
                    operation("regular", [item("hoodie", 5)], "express")
                self.assertEqual(self.path.read_bytes(), before)  # Check that the saved file has the same contents.

    def test_cli_quote_place_defaults_and_help(self):  # Test client quote place defaults and help.
        for action in ("quote", "place"):
            with self.subTest(action=action):  # Label each case separately in the test output.
                result = self.command(
                    action, "--customer", "student", "--fulfillment", "express",  # Use the requested delivery option or the pickup option by default.
                    "--item", "hoodie:2",
                )  # End this list, mapping, or function call.
                self.assertEqual(result.returncode, 0, result.stderr)
                order = json.loads(result.stdout)  # Decode the command output into Python data.
                self.assertEqual(order["fulfillment"], "express")
                self.assertEqual(order["total_cents"], 8400)  # Check the final amount in cents.
                self.assertIn("express", self.command(action, "--help").stdout)

        default = json.loads(self.command("quote", "--item", "notebook:2").stdout)  # Decode the command output into Python data.
        self.assertEqual((default["customer_type"], default["fulfillment"]), ("regular", "pickup"))
        invalid = self.command("place", "--fulfillment", "overnight", "--item", "notebook:2")  # Use the requested delivery option or the pickup default.
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(len(self.service.list_orders()), 1)  # Compare the saved order history with the expected records.

    def test_menu_quote_and_confirmed_order(self):  # Test menu quote and confirmed order.
        # Feed answers to the real menu and check the saved express order.
        result = self.command(inputs=(  # Run the command with these test inputs.
            "2\n\nnotebook\n2\n\nexpress\n"
            "3\n\nnotebook\n2\n\nexpress\ny\n0\n"  # Place and confirm the express order, then exit.
        ))
        self.assertEqual(result.returncode, 0, result.stderr)  # Check the command exit status.
        self.assertIn("pickup/delivery/express", result.stdout)
        self.assertIn("Quote only: no stock reserved and no order created.", result.stdout)  # Check that the text we are expecting appears in the command output.
        self.assertEqual(result.stdout.count("Total: $22.00"), 3)
        order, = self.service.list_orders()  # Read the single saved order.
        self.assertEqual(order["fulfillment"], "express")
        self.assertEqual(order["total_cents"], 2200)  # Check the final amount in cents.
        self.assertEqual(self.stock("notebook"), 18)

