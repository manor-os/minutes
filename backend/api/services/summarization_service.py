"""
AI-powered summarization service — uses OpenRouter (same key as multi-agent).
"""
from typing import Any, Dict, List, Optional
from loguru import logger

from .llm_config import get_openrouter_client, get_llm_model
from .meeting_templates import get_template


class SummarizationService:
    """Service for generating meeting summaries and extracting key points"""

    def __init__(self):
        self.client = get_openrouter_client()
        self.model = get_llm_model()
        logger.info(f"SummarizationService: model={self.model}")

    @staticmethod
    def _extract_usage(response) -> Dict[str, int]:
        """Extract token counts from an OpenAI-compatible response."""
        usage = response.usage
        return {
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }
    
    def summarize(self, transcript: str, max_length: int = 500, template_id: str = "general") -> tuple:
        """
        Generate a concise summary of the meeting transcript

        Args:
            transcript: Meeting transcript text
            max_length: Maximum length of summary in characters
            template_id: Meeting template to use for prompt guidance

        Returns:
            Tuple of (meeting summary, token_info dict)
        """
        # Validate transcript before processing
        if not transcript or len(transcript.strip()) < 10:
            logger.warning("Transcript is too short or empty")
            return "The meeting transcript was too short or contained no substantial content. Please ensure audio was recorded properly.", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        # Check if transcript is very short (likely noise)
        words = transcript.split()
        if len(words) < 5:
            logger.warning(f"Transcript has very few words ({len(words)}), may be corrupted")
            return f"The meeting transcript appears to be very short ({len(transcript)} characters, {len(words)} words) or may contain only background noise. Please ensure clear audio was recorded.", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        try:
            template = get_template(template_id)
            prompt = f"""You are a professional meeting note taker. {template['summary_prompt']}

IMPORTANT: When mentioning what was said, identify which speaker said it (e.g., "Speaker 1 mentioned...", "John suggested..."). This helps distinguish different participants' contributions.

If the transcript appears to be corrupted, contains only background noise, repetitive text, or is non-substantive (less than 20 meaningful words), please respond with: "The meeting transcript appears to be corrupted or contains non-substantive text. No key decisions, action items, or discussions could be identified for summary."

Meeting Transcript:
{transcript}

Professional Meeting Summary:"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional meeting note taker. Create clear, well-structured summaries with proper formatting. Use markdown formatting for structure (headers, bullet points, bold text). Focus on key decisions, action items, and important discussions. If the transcript is corrupted or non-substantive, clearly state that."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent, professional output
                max_tokens=1500  # Increased for more detailed summaries
            )
            
            summary = response.choices[0].message.content.strip()
            token_info = self._extract_usage(response)
            logger.info(f"Summary generated successfully. Tokens: {token_info['total_tokens']}")
            return summary, token_info
            
        except Exception as e:
            logger.error(f"Summarization failed: {str(e)}")
            raise Exception(f"Summarization failed: {str(e)}")
    
    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Calculate cost based on model and token usage
        Pricing as of 2024 (in USD per 1K tokens)
        """
        # DeepSeek pricing
        if "deepseek" in model.lower():
            # DeepSeek Chat: $0.14 per 1M input tokens, $0.28 per 1M output tokens
            input_cost = (prompt_tokens / 1_000_000) * 0.14
            output_cost = (completion_tokens / 1_000_000) * 0.28
            return round(input_cost + output_cost, 6)
        
        # OpenAI GPT-4 pricing
        elif "gpt-4" in model.lower():
            if "turbo" in model.lower() or "o" in model.lower():
                # GPT-4 Turbo: $0.01 per 1K input, $0.03 per 1K output
                input_cost = (prompt_tokens / 1_000) * 0.01
                output_cost = (completion_tokens / 1_000) * 0.03
            else:
                # GPT-4: $0.03 per 1K input, $0.06 per 1K output
                input_cost = (prompt_tokens / 1_000) * 0.03
                output_cost = (completion_tokens / 1_000) * 0.06
            return round(input_cost + output_cost, 6)
        
        # GPT-3.5 / GPT-4o-mini pricing
        elif "gpt-3.5" in model.lower() or "gpt-4o-mini" in model.lower():
            # $0.0015 per 1K input, $0.006 per 1K output
            input_cost = (prompt_tokens / 1_000) * 0.0015
            output_cost = (completion_tokens / 1_000) * 0.006
            return round(input_cost + output_cost, 6)
        
        # Default: estimate based on average
        else:
            # Conservative estimate: $0.002 per 1K tokens
            total_tokens = prompt_tokens + completion_tokens
            return round((total_tokens / 1_000) * 0.002, 6)
    
    def extract_key_points(self, transcript: str, num_points: int = 5, template_id: str = "general") -> tuple:
        """
        Extract key points from meeting transcript

        Args:
            transcript: Meeting transcript text
            num_points: Number of key points to extract
            template_id: Meeting template to use for prompt guidance

        Returns:
            Tuple of (list of key points, token_info dict)
        """
        try:
            template = get_template(template_id)
            prompt = f"""{template['key_points_prompt']}

Extract up to {num_points} points. Each point should be clear and concise. Format as a bulleted list.

Meeting Transcript:
{transcript}

Key Points:"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional meeting note taker. Extract the most important points from meetings. Focus on decisions, outcomes, and key discussions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent output
                max_tokens=800  # Increased for more detailed key points
            )
            
            content = response.choices[0].message.content.strip()
            token_info = self._extract_usage(response)

            # Parse bullet points
            key_points = [
                point.strip().lstrip('-•* ')
                for point in content.split('\n')
                if point.strip() and (point.strip().startswith('-') or point.strip().startswith('•') or point.strip().startswith('*'))
            ]
            
            # If no bullet points found, split by lines
            if not key_points:
                key_points = [line.strip() for line in content.split('\n') if line.strip()][:num_points]
            
            logger.info(f"Extracted {len(key_points)} key points. Tokens: {token_info['total_tokens']}")
            return key_points[:num_points], token_info
            
        except Exception as e:
            logger.error(f"Key points extraction failed: {str(e)}")
            # Return empty list with zero tokens on failure
            return [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    def extract_action_items(self, transcript: str, template_id: str = "general") -> tuple:
        """
        Extract action items from meeting transcript

        Args:
            transcript: Meeting transcript text
            template_id: Meeting template to use for prompt guidance

        Returns:
            Tuple of (list of action items, token_info dict)
        """
        try:
            template = get_template(template_id)
            prompt = f"""{template['action_items_prompt']}

For each action item, identify:
1. **Task Description**: Clear, actionable description of what needs to be done
2. **Assignee**: The person responsible (if mentioned, otherwise use "TBD" or "Team")
3. **Due Date**: The deadline or timeline (if mentioned, otherwise use "TBD")

Requirements:
- Only include actual action items (tasks that need to be completed)
- Be specific and actionable
- If no action items are found, return an empty array

Format as JSON array with keys: task, assignee, due_date

Meeting Transcript:
{transcript}

Action Items (JSON format):"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional meeting note taker. Extract action items in JSON format. Be precise and only include actual actionable tasks with clear descriptions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent output
                response_format={"type": "json_object"},
                max_tokens=1500  # Increased for more detailed action items
            )
            
            token_info = self._extract_usage(response)

            import json
            result = json.loads(response.choices[0].message.content)
            
            # Handle different response formats
            if "action_items" in result:
                action_items = result["action_items"]
            elif isinstance(result, list):
                action_items = result
            elif isinstance(result, dict) and "task" in result:
                # Single action item
                action_items = [result]
            else:
                action_items = []
            
            # Validate and clean action items
            cleaned_items = []
            for item in action_items:
                if isinstance(item, dict):
                    cleaned_item = {
                        "task": item.get("task", "").strip(),
                        "assignee": item.get("assignee", "TBD").strip(),
                        "due_date": item.get("due_date", "TBD").strip()
                    }
                    # Only include if task is not empty
                    if cleaned_item["task"]:
                        cleaned_items.append(cleaned_item)
            
            logger.info(f"Extracted {len(cleaned_items)} action items. Tokens: {token_info['total_tokens']}")
            return cleaned_items, token_info
            
        except Exception as e:
            logger.error(f"Action items extraction failed: {str(e)}")
            return [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    def generate_meeting_notes(self, transcript: str, template_id: str = "general") -> dict:
        """
        Generate comprehensive meeting notes including summary, key points, and action items

        Args:
            transcript: Meeting transcript text
            template_id: Meeting template to use for prompt guidance

        Returns:
            Dictionary with summary, key_points, and action_items
        """
        # Check if transcript is too short
        if not transcript or len(transcript.strip()) < 10:
            logger.warning("Transcript too short for meeting notes generation")
            return {
                "summary": "The meeting transcript was too short or contained no substantial content.",
                "key_points": [],
                "action_items": [],
                "token_cost": {
                    "summary": {"tokens": 0, "cost": 0.0},
                    "key_points": {"tokens": 0, "cost": 0.0},
                    "action_items": {"tokens": 0, "cost": 0.0},
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "currency": "USD"
                }
            }
        
        try:
            _ZERO_TOKENS: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            def _cost_entry(tokens: Dict[str, int]) -> Dict[str, Any]:
                cost = self._calculate_cost(self.model, tokens["prompt_tokens"], tokens["completion_tokens"])
                return {**tokens, "tokens": tokens["total_tokens"], "cost": round(cost, 6)}

            summary, summary_tokens = self.summarize(transcript, template_id=template_id)

            key_points: List = []
            action_items: List = []
            key_points_tokens = dict(_ZERO_TOKENS)
            action_items_tokens = dict(_ZERO_TOKENS)

            if "corrupted" not in summary.lower() and "non-substantive" not in summary.lower():
                try:
                    key_points, key_points_tokens = self.extract_key_points(transcript, template_id=template_id)
                except Exception as e:
                    logger.warning(f"Key points extraction failed: {str(e)}")

                try:
                    action_items, action_items_tokens = self.extract_action_items(transcript, template_id=template_id)
                except Exception as e:
                    logger.warning(f"Action items extraction failed: {str(e)}")
            else:
                logger.info("Skipping key points and action items extraction due to corrupted transcript")

            all_tokens = [summary_tokens, key_points_tokens, action_items_tokens]
            total_prompt = sum(t.get("prompt_tokens", 0) for t in all_tokens)
            total_completion = sum(t.get("completion_tokens", 0) for t in all_tokens)

            return {
                "summary": summary,
                "key_points": key_points,
                "action_items": action_items,
                "token_cost": {
                    "summary": _cost_entry(summary_tokens),
                    "key_points": _cost_entry(key_points_tokens),
                    "action_items": _cost_entry(action_items_tokens),
                    "total_tokens": total_prompt + total_completion,
                    "total_cost": round(sum(
                        self._calculate_cost(self.model, t["prompt_tokens"], t["completion_tokens"])
                        for t in all_tokens
                    ), 6),
                    "currency": "USD",
                    "model": self.model,
                },
            }
            
        except Exception as e:
            logger.error(f"Meeting notes generation failed: {str(e)}")
            # Return a basic response instead of raising
            return {
                "summary": f"Error generating meeting notes: {str(e)}",
                "key_points": [],
                "action_items": [],
                "token_cost": {
                    "summary": {"tokens": 0, "cost": 0.0},
                    "key_points": {"tokens": 0, "cost": 0.0},
                    "action_items": {"tokens": 0, "cost": 0.0},
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "currency": "USD"
                }
            }

