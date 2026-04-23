from pricing_tool import pricing_tool
from item_details_tool import item_details_tool
from catalog_tool import catalog_tool
from collection_tool import collection_tool
from custom_order_enquiry_tool import custom_order_enquiry_tool
from shipping_enquiry_tool import shipping_enquiry_tool
from returns_enquiry_tool import returns_enquiry_tool
from order_status_enquiry_tool import order_status_enquiry_tool
from other_item_related_enquiry_tool import other_item_related_enquiry_tool



TOOLS= [
    {
        "name" : "get_item_price",
        "description" : "Get the price of an item by name",
        "input_schema" : {
            "type" : "object",
            "properties" : {
                "item_name" : {"type" : "string"}
            },
            "required" : ["item_name"]
        }
    }, 

    {
        "name": "get_item_details",
        "description": "Get the details about an item by name",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_name": {"type": "string"}
            },
            "required": ["item_name"]
        }
    },

     {
        "name" : "view_catalog_items",
        "description" : "give users the details of all the items in catalog of the specific collection",
        "input_schema" : {
            "type" : "object",
            "properties" : {
                "collection_name" : {"type" : "string"}
            },
            "required" : ["collection_name"]
        }
    }, 

    {
        "name" : "view_collection",
        "description" : "give user a description of the available collections, their details and a brief description of items in collection",
        "input_schema" : {
            "type" : "object",
            "properties" : {
                "user_query" : {"type" : "string"}
            },
            "required" : ["user_query"]
        }
    }, 

    {
        "name" : "custom_order_enquiry",
        "description" : "User wants to place/enquire about a custom order",
        "input_schema" : {
            "type" : "object",
            "properties" : {
                "user_query" : {"type" : "string"}
            },
            "required" : ["user_query"]
        }
    }, 

    {
        "name" : "shipping_enquiry",
        "description" : "User wants to enquire about shipping options",
        "input_schema" : {
            "type" : "object",
            "properties" : {
                "user_query" : {"type" : "string"}
            },
            "required" : ["user_query"]
        }
    },

    {
        "name": "returns_enquiry",
        "description": "User wants to enquire about returns options",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_query": {"type": "string"}
            },
            "required": ["user_query"]
        }
    },

    {
        "name": "order_status_enquiry",
        "description": "User wants to enquire about an issue or something related to their order status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_query": {"type": "string"}
            },
            "required": ["user_query"]
        }
    },

    {
        "name": "other_item_related_enquiry",
        "description": "User wants to enquire about something else related to the item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_query": {"type": "string"}
            },
            "required": ["user_query"]
        }
    }

]

TOOL_IMPLEMENTATIONS = {
    "get_item_price" : pricing_tool, 
    "get_item_details" : item_details_tool, 
    "view_catalog_items" : catalog_tool, 
    "view_collection" : collection_tool, 
    "custom_order_enquiry" : custom_order_enquiry_tool,
    "shipping_enquiry" : shipping_enquiry_tool,
    "returns_enquiry" : returns_enquiry_tool,
    "other_item_related_enquiry" : other_item_related_enquiry_tool, 
}