import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from supplydesk.service import OrderService


def item(product_id, quantity):
    return {"product_id": product_id, "quantity": quantity}


class ExpressTests(unittest.TestCase):
    def setUp(self):
        # Give every test a fresh save file so tests do not change real orders.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state.json"
        self.service = OrderService(self.path)

    def command(self, *args, inputs=None):
        return subprocess.run(
            [sys.executable, "-m", "supplydesk", "--data", str(self.path), *args],
            input=inputs, text=True, capture_output=True, timeout=10,
        )

    def stock(self, product_id):
        return next(p["stock"] for p in self.service.catalog()
                    if p["product_id"] == product_id)

    def test_express_examples(self):
        # Use the three examples from the change request as expected totals.
        cases = [
            ("regular", "notebook", 2, 1000, 0, 2200),
            ("student", "hoodie", 2, 8000, 800, 8400),
            ("regular", "hoodie", 3, 12000, 0, 13200),
        ]
        for customer, product, quantity, subtotal, discount, total in cases:
            with self.subTest(customer=customer, product=product, quantity=quantity):
                quote = self.service.quote(customer, [item(product, quantity)], "express")
                self.assertEqual(quote["fulfillment"], "express")
                self.assertEqual(quote["subtotal_cents"], subtotal)
                self.assertEqual(quote["discount_cents"], discount)
                self.assertEqual(quote["delivery_cents"], 1200)
                self.assertEqual(quote["total_cents"], total)
        self.assertFalse(self.path.exists())

    def test_student_eligibility_matches_existing_pickup(self):
        # Compare the student discount with pickup on both sides of the threshold.
        for quantity in (9, 10, 11):
            with self.subTest(quantity=quantity):
                items = [item("notebook", quantity)]
                pickup = self.service.quote("student", items)
                express = self.service.quote("student", items, "express")
                self.assertEqual(express["discount_cents"], pickup["discount_cents"])
                self.assertEqual(express["total_cents"], pickup["total_cents"] + 1200)

    def test_standard_threshold_uses_discounted_subtotal(self):
        # Check below and at the free standard delivery threshold, including a discount.
        cases = [
            ("regular", [item("notebook", 19)], 600),
            ("regular", [item("notebook", 20)], 0),
            ("regular", [item("hoodie", 3)], 0),
            ("student", [item("notebook", 20)], 600),
        ]
        for customer, items, fee in cases:
            with self.subTest(customer=customer, items=items):
                standard = self.service.quote(customer, items, "delivery")
                self.assertEqual(standard["delivery_cents"], fee)
                self.assertEqual(self.service.quote(customer, items)["delivery_cents"], 0)
                self.assertEqual(
                    self.service.quote(customer, items, "express")["delivery_cents"], 1200
                )

    def test_order_snapshot_stock_history_and_numbering(self):
        # Follow an express order from quote to placement, reopening, and cancellation.
        items = [item("hoodie", 2), item("notebook", 1)]
        quote = self.service.quote("student", items, "express")
        order = self.service.place_order("student", items, "express")
        expected = {"order_id": "ORD-0001", "status": "placed", **quote}
        self.assertEqual(order, expected)
        self.assertEqual((self.stock("hoodie"), self.stock("notebook")), (3, 19))
        self.assertEqual(self.service.get_order("ORD-0001"), expected)

        reopened = OrderService(self.path)
        self.assertEqual(reopened.list_orders(), [expected])
        self.assertEqual(reopened.get_order("ORD-0001"), expected)
        cancelled = {**expected, "status": "cancelled"}
        self.assertEqual(reopened.cancel_order("ORD-0001"), cancelled)
        self.assertEqual((self.stock("hoodie"), self.stock("notebook")), (5, 20))
        second = reopened.place_order("regular", [item("notebook", 1)])
        self.assertEqual(second["order_id"], "ORD-0002")
        self.assertEqual(second["fulfillment"], "pickup")
        self.assertEqual(OrderService(self.path).list_orders(), [cancelled, second])

    def test_invalid_fulfillment_and_stock_preserve_state(self):
        # Compare the save file before and after rejected requests.
        self.service.place_order("regular", [item("hoodie", 1)])
        before = self.path.read_bytes()
        for operation in (self.service.quote, self.service.place_order):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "Fulfillment"):
                    operation("regular", [item("notebook", 1)], "overnight")
                with self.assertRaisesRegex(ValueError, "Not enough stock"):
                    operation("regular", [item("hoodie", 5)], "express")
                self.assertEqual(self.path.read_bytes(), before)

    def test_cli_quote_place_defaults_and_help(self):
        for action in ("quote", "place"):
            with self.subTest(action=action):
                result = self.command(
                    action, "--customer", "student", "--fulfillment", "express",
                    "--item", "hoodie:2",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                order = json.loads(result.stdout)
                self.assertEqual(order["fulfillment"], "express")
                self.assertEqual(order["total_cents"], 8400)
                self.assertIn("express", self.command(action, "--help").stdout)

        default = json.loads(self.command("quote", "--item", "notebook:2").stdout)
        self.assertEqual((default["customer_type"], default["fulfillment"]), ("regular", "pickup"))
        invalid = self.command("place", "--fulfillment", "overnight", "--item", "notebook:2")
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(len(self.service.list_orders()), 1)

    def test_menu_quote_and_confirmed_order(self):
        # Feed answers to the real menu and check the saved express order.
        result = self.command(inputs=(
            "2\n\nnotebook\n2\n\nexpress\n"
            "3\n\nnotebook\n2\n\nexpress\ny\n0\n"
        ))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pickup/delivery/express", result.stdout)
        self.assertIn("Quote only: no stock reserved and no order created.", result.stdout)
        self.assertEqual(result.stdout.count("Total: $22.00"), 3)
        order, = self.service.list_orders()
        self.assertEqual(order["fulfillment"], "express")
        self.assertEqual(order["total_cents"], 2200)
        self.assertEqual(self.stock("notebook"), 18)

