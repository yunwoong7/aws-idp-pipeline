import logging
import os

from mcp.server.fastmcp import FastMCP

from config import get_app_config
from tools.search_tools import hybrid_search
from tools.document_analyzer import get_document_analysis, get_page_analysis_details, get_document_info
# from tools.document_list import get_documents_list
from tools.basic_tools import add, echo
from tools.user_content_manager import add_user_content_to_page, remove_user_content_from_page
from tools.document_analyzer import get_segment_image_attachment

# Set logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Get configuration
conf = get_app_config()

MODEL_ID = conf['model_id']

# Create MCP server
mcp = FastMCP("AWS IDP AI Analysis Server", port=int(conf['port']))


# Register tools with names and descriptions
mcp.add_tool(get_document_info)
mcp.add_tool(hybrid_search)
mcp.add_tool(get_document_analysis)
mcp.add_tool(get_page_analysis_details)
# Register segment image attachment tool
mcp.add_tool(get_segment_image_attachment)
# mcp.add_tool(get_documents_list)
mcp.add_tool(add)
mcp.add_tool(echo)
mcp.add_tool(add_user_content_to_page)
mcp.add_tool(remove_user_content_from_page)


def main():
    print("\n" + "=" * 50)
    print(f"MODEL_ID: {MODEL_ID}")
    print(f"API_BASE_URL: {conf['api_base_url']}")
    print(f"PORT: {conf['port']}")
    print(f"Press Ctrl+C to exit.")
    print(f"Starting AWS IDP AI Analysis Server...")
    print("=" * 50 + "\n")

    mcp.run()


if __name__ == "__main__":
    main() 