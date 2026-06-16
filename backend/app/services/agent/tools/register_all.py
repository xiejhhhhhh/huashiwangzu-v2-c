from app.services.agent.tools.registry import tool_registry
from app.services.agent.tools.search_knowledge import SearchKnowledgeTool
from app.services.agent.tools.get_page_fusion import GetPageFusionTool
from app.services.agent.tools.read_evidence import ReadEvidenceTool
from app.services.agent.tools.read_chunk import ReadChunkTool
from app.services.agent.tools.read_entity import ReadEntityTool
from app.services.agent.tools.read_file import ReadFileTool
from app.services.agent.tools.read_graph_context import ReadGraphContextTool
from app.services.agent.tools.read_latest_evaluation import ReadLatestEvaluationTool
from app.services.agent.tools.read_pending_candidates import ReadPendingCandidatesTool
from app.services.agent.tools.read_system_status import ReadSystemStatusTool


def register_all_tools():
    tool_registry.register(SearchKnowledgeTool())
    tool_registry.register(GetPageFusionTool())
    tool_registry.register(ReadChunkTool())
    tool_registry.register(ReadEntityTool())
    tool_registry.register(ReadEvidenceTool())
    tool_registry.register(ReadFileTool())
    tool_registry.register(ReadGraphContextTool())
    tool_registry.register(ReadPendingCandidatesTool())
    tool_registry.register(ReadLatestEvaluationTool())
    tool_registry.register(ReadSystemStatusTool())
