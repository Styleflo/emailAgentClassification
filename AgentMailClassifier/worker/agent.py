from .state import WorkerState
from .nodes import clean_node, classify_node, move_email_node
from functools import partial
from langgraph.graph import END, START, StateGraph

def create_worker_graph(imap_pool):
    workflow = StateGraph(WorkerState)

    # Ajout des nœuds (injection du pool IMAP via partial)
    workflow.add_node("clean", clean_node)
    workflow.add_node("classify", classify_node)
    workflow.add_node(
        "move_email", partial(move_email_node, imap_pool=imap_pool)
    )

    # Définition du flux séquentiel
    workflow.add_edge(START, "clean")
    workflow.add_edge("clean", "classify")
    workflow.add_edge("classify", "move_email")
    workflow.add_edge("move_email", END)

    return workflow.compile()