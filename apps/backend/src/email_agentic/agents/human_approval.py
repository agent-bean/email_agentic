from langgraph.types import interrupt


class HumanApprovalAgent:
    def wait(self, kind, entity_id):
        # On resume the workflow reloads the authoritative decision from the database.
        return interrupt({"kind": kind, "entity_id": str(entity_id)})
