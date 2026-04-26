"""
Meeting templates — tailored summarization prompts for different meeting types.
"""

TEMPLATES = {
    "general": {
        "name": "General Meeting",
        "description": "Default template for any meeting",
        "summary_prompt": "Summarize this meeting transcript concisely. Highlight the main topics discussed, decisions made, and any conclusions reached.",
        "key_points_prompt": "Extract the key points and important takeaways from this meeting transcript. Return as a JSON array of strings.",
        "action_items_prompt": "Extract action items from this meeting transcript. For each, include: description, assignee (if mentioned), and deadline (if mentioned). Return as a JSON array of objects with keys: description, assignee, deadline.",
    },
    "standup": {
        "name": "Daily Standup",
        "description": "Scrum-style daily standup",
        "summary_prompt": "Summarize this daily standup meeting. For each participant, list: (1) What they did yesterday, (2) What they plan to do today, (3) Any blockers. End with a brief team status overview.",
        "key_points_prompt": "Extract the key updates from this standup. Focus on: completed work, planned work, and blockers. Return as a JSON array of strings.",
        "action_items_prompt": "Extract blockers and action items from this standup. Focus on items that need resolution. Return as a JSON array of objects with keys: description, assignee, deadline.",
    },
    "one_on_one": {
        "name": "1-on-1",
        "description": "Manager-report 1:1 meeting",
        "summary_prompt": "Summarize this 1:1 meeting between a manager and their report. Cover: career development topics, feedback given/received, concerns raised, goals discussed, and personal check-in notes.",
        "key_points_prompt": "Extract the key discussion points from this 1:1. Focus on: feedback, goals, concerns, and development items. Return as a JSON array of strings.",
        "action_items_prompt": "Extract follow-up items from this 1:1 meeting. Include both manager and report action items. Return as a JSON array of objects with keys: description, assignee, deadline.",
    },
    "retrospective": {
        "name": "Retrospective",
        "description": "Sprint or project retrospective",
        "summary_prompt": "Summarize this retrospective meeting. Organize into: (1) What went well, (2) What didn't go well, (3) What to improve. End with the team's agreed-upon improvement actions.",
        "key_points_prompt": "Extract insights from this retrospective. Categorize as: went_well, needs_improvement, or action. Return as a JSON array of strings.",
        "action_items_prompt": "Extract improvement actions the team agreed on. Return as a JSON array of objects with keys: description, assignee, deadline.",
    },
    "brainstorm": {
        "name": "Brainstorm",
        "description": "Ideation and brainstorming session",
        "summary_prompt": "Summarize this brainstorming session. List all ideas discussed, group them by theme if possible, and highlight which ideas had the most support or were selected for further exploration.",
        "key_points_prompt": "Extract the main ideas and themes from this brainstorm. Return as a JSON array of strings.",
        "action_items_prompt": "Extract next steps for exploring the ideas discussed. Return as a JSON array of objects with keys: description, assignee, deadline.",
    },
    "client_call": {
        "name": "Client Call",
        "description": "External client or customer meeting",
        "summary_prompt": "Summarize this client meeting. Cover: client requirements discussed, questions raised, commitments made, timeline discussed, and any concerns or risks identified.",
        "key_points_prompt": "Extract key client requirements, decisions, and commitments from this meeting. Return as a JSON array of strings.",
        "action_items_prompt": "Extract all commitments and follow-up items from this client call. Distinguish between items for our team and items for the client. Return as a JSON array of objects with keys: description, assignee, deadline.",
    },
    "interview": {
        "name": "Interview",
        "description": "Job interview or candidate evaluation",
        "summary_prompt": "Summarize this interview. Cover: candidate background discussed, key questions asked, candidate responses and strengths/weaknesses observed, technical assessment results, and overall impression.",
        "key_points_prompt": "Extract key observations about the candidate from this interview. Return as a JSON array of strings.",
        "action_items_prompt": "Extract follow-up items (reference checks, next round scheduling, decision timeline). Return as a JSON array of objects with keys: description, assignee, deadline.",
    },
}


def get_template(template_id: str) -> dict:
    """Get a template by ID, falling back to general."""
    return TEMPLATES.get(template_id, TEMPLATES["general"])


def get_all_templates() -> list:
    """Return all templates as a list for the frontend."""
    return [
        {"id": k, **{kk: vv for kk, vv in v.items() if kk in ("name", "description")}}
        for k, v in TEMPLATES.items()
    ]
