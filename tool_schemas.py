"""Anthropic tool JSON schemas only — no tool implementations (avoids circular imports)."""

TOOLS = [
    {
        "name": "item_details_tool",
        "description": "Used when user wants details of a specific item: price, material, size, weight, dimensions. User must provide the item name. Not for order, returns, or shipping questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_name": {
                    "type": "string",
                    "description": "The name of the item the user wants details for",
                }
            },
            "required": ["item_name"],
        },
    },
    {
        "name": "collection_inquiry",
        "description": (
            "Used when the customer wants to browse the catalog (list collections, "
            "see items by type, view items in a collection) or learn about a "
            "collection's story, mood, or aesthetic. Not for a specific named item's "
            "price or material."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_query": {
                    "type": "string",
                    "description": "The customer's collection or catalog browse request",
                }
            },
            "required": ["user_query"],
        },
    },
    {
        "name": "custom_order_enquiry_tool",
        "description": "Used when user wants to place or enquire about a custom order, share inspiration, or ask custom order questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "custom_order_enquiry_query": {
                    "type": "string",
                    "description": "The user's custom order query or inspiration",
                }
            },
            "required": ["custom_order_enquiry_query"],
        },
    },
    {
        "name": "shipping_enquiry_tool",
        "description": "Used for shipping option, method, or cost questions only. Not for order status or returns questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "shipping_enquiry_query": {
                    "type": "string",
                    "description": "The user's shipping enquiry",
                }
            },
            "required": ["shipping_enquiry_query"],
        },
    },
    {
        "name": "returns_enquiry_tool",
        "description": "Used for returns policy or timeline questions only. Not for order status or shipping questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "returns_enquiry_query": {
                    "type": "string",
                    "description": "The user's returns enquiry",
                }
            },
            "required": ["returns_enquiry_query"],
        },
    },
]
