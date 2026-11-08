
"""A small starting test suite for the order desk."""

from pathlib import Path
import tempfile
import unittest

from supplydesk.service import OrderService


class OrderSmokeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def test_regular_pickup_quote(self):
        quote = self.service.quote("regular", [{"product_id": "notebook", "quantity": 2}])
        self.assertEqual(quote["subtotal_cents"], 1000)
        self.assertEqual(quote["discount_cents"], 0)
        self.assertEqual(quote["delivery_cents"], 0)
        self.assertEqual(quote["total_cents"], 1000)

    def test_student_delivery_quote(self):
        quote = self.service.quote("student", [{"product_id": "hoodie", "quantity": 2}], "delivery")
        self.assertEqual(quote["discount_cents"], 800)
        self.assertEqual(quote["delivery_cents"], 600)
        self.assertEqual(quote["total_cents"], 7800)

    def test_order_can_be_reopened(self):
        order = self.service.place_order("regular", [{"product_id": "mug", "quantity": 1}])
        self.assertEqual(order["order_id"], "ORD-0001")
        self.assertEqual(order["status"], "placed")
        self.assertEqual(OrderService(self.path).get_order(order["order_id"]), order)

    def test_cancel_order_restores_stock(self):
        before = self.service.catalog()
        order = self.service.place_order("regular", [{"product_id": "pen-pack", "quantity": 2}])
        cancelled = self.service.cancel_order(order["order_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.service.catalog(), before)

    # This is the tests Im adding

    #testing normal behaviour
    def test_order_reduces_stock(self):
        # Get the original amount of notebook stock
        before = self.service.catalog()
        original_stock = next(
            p["stock"] for p in before
            if p["product_id"] == "notebook"
        )

        # Place an order for 2 more notebooks
        order = self.service.place_order(
            "regular",
            [{"product_id": "notebook", "quantity": 2}]
        )

        # Get the new updated stock
        after = self.service.catalog()
        new_stock = next(
            p["stock"] for p in after
            if p["product_id"] == "notebook"
        )

        # make sure that the stock actually decreased by 2
        self.assertEqual(new_stock, original_stock - 2)

        # Check that the order was actually placed
        self.assertEqual(order["status"], "placed")

    #testing boundary behaviour
    def test_zero_quantity(self):
        # Try to order zero notebooks
        with self.assertRaises(ValueError):
            self.service.place_order(
                "regular",
                [{"product_id": "notebook", "quantity": 0}]
                
            )

    
    # testing invalid behaviour
    def test_invalid_product(self):
        # Try to order a product that does not exist
        with self.assertRaises(ValueError):
            self.service.place_order(
                "regular",
                [{"product_id": "fake-product", "quantity": 1}]
            )

    
    # testing behaviour important to preserve
    def test_quote_does_not_change_stock(self):
        # Get the original inventory
        before = self.service.catalog()

        # Request a quote without placing an order
        self.service.quote(
            "regular",
            [{"product_id": "notebook", "quantity": 2}]
        )

        # Get the inventory after the quote
        after = self.service.catalog()

        # Make sure the inventory has not changed
        self.assertEqual(before, after)




if __name__ == "__main__":
    unittest.main()
