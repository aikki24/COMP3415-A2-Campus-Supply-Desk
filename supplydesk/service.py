"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore


# The service and command-line parser use the same delivery choices.
FULFILLMENT_OPTIONS = ("pickup", "delivery", "express")  # this is the list of the supported fulfillment choices.
EXPRESS_DELIVERY_CENTS = 1200


class OrderService:
    def __init__(self, state_path=".supplydesk/state.json"):
        self.store = JsonStore(state_path)

    def catalog(self):
        return self.store.load()["catalog"]

    def quote(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        return self._price_request(state, customer_type, items, fulfillment)  # Return the shared calculation without saving an order to differantiate between quote and sale.

    def _price_request(self, state, customer_type, items, fulfillment):  # Use one pricing section for both the quotes and orders.
        # Quotes and orders share these checks and calculations so their totals agree instead of doing them twice seperarlty (code smells fix instead of repeating code we use a shared function).
        if customer_type not in ("regular", "student"):  # make sure and check that the customer type is not currently in ("regular", "student").
            raise ValueError("Customer type must be regular or student.")
        if fulfillment not in FULFILLMENT_OPTIONS:  # Reject any choices taht are outside the supported list.
            raise ValueError("Fulfillment must be pickup, delivery, or express.")
        if not isinstance(items, list) or not items:  # Check not isinstance(items, list) or not items.
            raise ValueError("An order must contain at least one item.")
        lines = self._build_lines(state["catalog"], items)  # Check the items against the currently displayed catalog.
        subtotal = sum(line["line_total_cents"] for line in lines)
        # calcualtion of the student discount on stuff before adding delivery cost.
        discount = 0  # Set discount.
        if customer_type == "student" and subtotal > 5000:
            discount = (subtotal * 10 + 50) // 100  # Set discount.
        delivery = 0
        # Express always costs $12 no matter what. Only standard delivery can qualify for a waiver.
        if fulfillment == "express":  # Apply the fixed fee whenever express is selected.
            delivery = EXPRESS_DELIVERY_CENTS
        elif fulfillment == "delivery" and subtotal - discount < 10000:  # Check if the standard delivery still needs a fee.
            delivery = 600
        return {  # Build the item data that will be expected by the service.
            "customer_type": customer_type,
            "fulfillment": fulfillment,  # Record the fulfillment.
            "items": lines,
            "subtotal_cents": subtotal,  # Record the subtotal cents.
            "discount_cents": discount,
            "delivery_cents": delivery,  # Record the delivery cents.
            "total_cents": subtotal - discount + delivery,
        }  # End this list, mapping, or function call.

    def _build_lines(self, catalog, items):  # Turn the newly requested items into validated order lines.
        # Check each of the requested items and record the names, prices, and quantity for that order.
        lines = []  # Set lines.
        for item in items:
            if not isinstance(item, dict):  # Check not isinstance(item, dict).
                raise ValueError("Each item must contain a product_id and quantity.")
            product = None  # Set product.
            for candidate in catalog:
                if candidate["product_id"] == item.get("product_id"):  # Check if the product items match.
                    product = candidate
                    break  # Complete this step in the order or test flow.
            if product is None:
                raise ValueError("Unknown product.")  # Stop and report the invalid request.
            quantity = item.get("quantity")
            if type(quantity) is not int or quantity < 1 or quantity > 99:  # check if the quantity is an integer and within the range we want.
                raise ValueError("Quantity must be an integer from 1 to 99.")
            if quantity > product["stock"]:  # Check quantity > ["stock"].
                raise ValueError("Not enough stock for " + product["product_id"] + ".")
            line_total = product["unit_price_cents"] * quantity  # Set line total.
            lines.append({
                "product_id": product["product_id"],  # Record the product id.
                "name": product["name"],
                "unit_price_cents": product["unit_price_cents"],  # Record the unit price in cents.
                "quantity": quantity,
                "line_total_cents": line_total,  # Record the line total cents.
            })
        return lines  # Give the  lines back to pricing.

    def place_order(self, customer_type, items, fulfillment="pickup"):  # Validate, price, and save a new order.
        state = self.store.load()
        # Validate and price against the same stock data and then this order will update.
        priced = self._price_request(state, customer_type, items, fulfillment)  # Get the validated items and prices for this order.
        order = {
            "order_id": "ORD-" + str(state["next_order_number"]).zfill(4),  # Record the order id.
            "status": "placed",
            **priced,  # Copy the price breakdown and items into the new saved order.
        }
        for line in priced["items"]:  # Process each purchased line to deduct stock.
            for product in state["catalog"]:
                if product["product_id"] == line["product_id"]:  # Check if the product IDs match.
                    product["stock"] -= line["quantity"]
        state["next_order_number"] += 1  # Increment to the next order number.
        state["orders"].append(order)
        self.store.save(state)  # Complete this step in the order or test flow.
        return order

    def list_orders(self):
        return self.store.load()["orders"]

    def get_order(self, order_id):
        state = self.store.load()
        for order in state["orders"]:
            if order["order_id"] == order_id:
                return order
        raise ValueError("Unknown order: " + order_id)

    def cancel_order(self, order_id):
        state = self.store.load()
        order = None
        for candidate in state["orders"]:
            if candidate["order_id"] == order_id:
                order = candidate
                break
        if order is None:
            raise ValueError("Unknown order: " + order_id)
        for line in order["items"]:
            for product in state["catalog"]:
                if product["product_id"] == line["product_id"]:
                    product["stock"] += line["quantity"]
        order["status"] = "cancelled"
        self.store.save(state)
        return order
