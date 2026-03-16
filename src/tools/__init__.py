from .chatmsep_tool import chatmsep
from .pdf_extraction_tool import extract_full_plan_details
from .teaching_plan_tool import generate_teaching_plan
from .modify_teaching_plan import modify_teaching_plan
from .save_plan_tool import save_plan
from .document_analyzer_tool import document_analyzer
# from .web_search import tool as web_search_tool

tools = [
    chatmsep,
    extract_full_plan_details,
    generate_teaching_plan,
    modify_teaching_plan,
    save_plan,
    # web_search_tool,
    document_analyzer,
]