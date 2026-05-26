"""
# backend/core/chat/message_router.py

This file defines the router that parses and directs incoming messages.

Responsibilities:
1. Parse incoming text for @name (group tag) and /@name (private tag) mentions.
2. If @name is used, push the message to the public Team thread in the DB and alert the agent.
3. If /@name is used, push the message to the Agent's private memory thread ONLY.
4. Trigger the target Agent's ReACT loop via the EventBus.
"""

class MessageRouter:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        
    async def route_message(self, text: str, sender_id: str, team_id: str):
        # TODO: Parse @ and /@, update DB, trigger EventBus
        pass
