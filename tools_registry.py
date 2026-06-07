from tool_schemas import TOOLS
from collection_inquiry_tool import collection_inquiry
from item_details_tool import item_details_tool
from custom_order_enquiry_tool import custom_order_enquiry_tool
from shipping_enquiry_tool import shipping_enquiry_tool
from returns_enquiry_tool import returns_enquiry_tool

TOOL_IMPLEMENTATIONS = {
    "item_details_tool": item_details_tool,
    "collection_inquiry": collection_inquiry,
    "custom_order_enquiry_tool": custom_order_enquiry_tool,
    "shipping_enquiry_tool": shipping_enquiry_tool,
    "returns_enquiry_tool": returns_enquiry_tool,
}
