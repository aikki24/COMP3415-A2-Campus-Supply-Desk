"""Interactive terminal adapter; business rules remain in OrderService."""


def money(cents):
    return f"${cents // 100}.{cents % 100:02d}"


def show_catalog(products):
    print("\nProduct ID       Name                     Price     Stock")
    for product in products:
        print(f"{product['product_id']:<16} {product['name']:<24} "
              f"{money(product['unit_price_cents']):>8} {product['stock']:>8}")


def show_order(order):
    print("\n" + order.get("order_id", "Quote") + " - " + order.get("status", "not placed"))
    print(f"Customer: {order['customer_type']} | Fulfillment: {order['fulfillment']}")
    for line in order['items']:
        print(f"  {line['name']} x {line['quantity']}: {money(line['line_total_cents'])}")
    for label, key in (("Subtotal", "subtotal_cents"), ("Discount", "discount_cents"),
                       ("Delivery", "delivery_cents"), ("Total", "total_cents")):
        print(f"{label}: {money(order[key])}")


def read_request(service):
    show_catalog(service.catalog())
    print("Enter product IDs from the table. Blank product ID finishes the item list.")
    customer = input("Customer type [regular/student] (Enter = regular): ").strip() or "regular"
    items = []
    while True:
        product_id = input("Product ID (Enter = finish): ").strip()
        if not product_id:
            break
        raw = input("Quantity: ").strip()
        try:
            quantity = int(raw)
        except ValueError:
            print("Please enter a whole number. Re-enter this item.")
            continue
        items.append({"product_id": product_id, "quantity": quantity})
    # Pressing Enter still by default chooses pickup. Express is now available here too.
    fulfillment = input("Fulfillment [pickup/delivery/express] (Enter = pickup): ").strip() or "pickup"  # Ask how to fulfill the order and default it to pickup.
    return customer, items, fulfillment


def quote_request(service):  # Handle the menu option for all quotes.
    # Show the price without creating an order or reserving stock because its not a sale.
    show_order(service.quote(*read_request(service)))  # Display the calculated quote.
    print("Quote only: no stock reserved and no order created.")


def place_request(service):  # Handle the menu option for placing an order.
    # Preview the price first, then save only if the user confirms (price check then sale).
    request = read_request(service)  # Collect the customer, items, and fulfillment choice.
    show_order(service.quote(*request))
    if input("Place this order? [y/N]: ").strip().lower() == "y":  # Proceed when the user confirms with y.
        show_order(service.place_order(*request))
    else:  # Handle the other outcome of the check.
        print("Order not placed.")


def show_history(service):  # Handle the menu option for order history.
    # Show saved orders in the same order they were placed.
    orders = service.list_orders()  # Load saved orders.
    if not orders:
        print("No orders yet.")  # Show the result of the menu action.
    for order in orders:
        show_order(order)  # Display the details of this order.


def cancel_request(service):  # Handle the menu option for any cancellations.
    # Ask everytime before cancelling because cancellation changes the saved order and stock.
    order_id = input("Order ID to cancel: ").strip()  # Read the ID of the order to cancel.
    if input("Cancel this order? [y/N]: ").strip().lower() == "y":
        show_order(service.cancel_order(order_id))  # Cancel and display the selected order.
    else:
        print("Cancellation abandoned.")  # Show the result of the menu action.


def run_menu(service):
    # Each menu number points to the action it should run to be more organzied.
    actions = {  # Map each menu number to an action.
        "1": lambda: show_catalog(service.catalog()),
        "2": lambda: quote_request(service),  # Run a quote when selected.
        "3": lambda: place_request(service),
        "4": lambda: show_history(service),  # Run order history when selected.
        "5": lambda: show_order(service.get_order(input("Order ID: ").strip())),
        "6": lambda: cancel_request(service),  # Run cancellation when selected.
    }
    print("Campus Supply Desk | All prices are CAD. Orders are saved automatically.")
    while True:
        try:
            print("\n1. View products and stock\n2. Get a quote\n3. Place an order"
                  "\n4. View order history\n5. Find an order\n6. Cancel an order\n0. Exit")
            choice = input("Choose an option: ").strip()
            if choice == "0":
                print("Goodbye.")
                return 0
            action = actions.get(choice)  # Find the action for the entered number.
            if action is None:
                print("Choose a number from 0 to 6.")  # Show the result of the menu action.
            else:
                action()  # Run the selected action.
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0
        except (ValueError, OSError, KeyError, TypeError) as error:
            print(f"Error: {error}")
            print("Returning to the menu. Check your input or state file before retrying.")
