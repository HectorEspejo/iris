"""
ClubAI Response Aggregator

Combines responses from multiple subtasks into a coherent final response.
"""

import re
from typing import Optional
import structlog

from shared.models import TaskMode, SubtaskStatus
from .database import db

logger = structlog.get_logger()


class ResponseAggregator:
    """
    Aggregates responses from distributed subtasks into a final response.

    Strategies by mode:
    - SUBTASKS: Combine responses in order, adding structure
    - CONSENSUS: Compare responses, detect outliers, choose best
    - CONTEXT: Synthesize partial analyses into summary
    """

    async def aggregate(
        self,
        task_id: str,
        mode: TaskMode,
        original_prompt: str
    ) -> str:
        """
        Aggregate subtask responses into a final response.

        Args:
            task_id: The parent task ID
            mode: Task division mode
            original_prompt: Original user prompt

        Returns:
            Aggregated response string
        """
        # Get all subtasks
        subtasks = await db.get_subtasks_by_task(task_id)

        if not subtasks:
            return "No results available."

        # Filter to completed subtasks
        completed = [
            s for s in subtasks
            if s["status"] == SubtaskStatus.COMPLETED.value and s["response"]
        ]

        if not completed:
            failed_count = len([s for s in subtasks if s["status"] == SubtaskStatus.FAILED.value])
            timeout_count = len([s for s in subtasks if s["status"] == SubtaskStatus.TIMEOUT.value])
            return f"Task failed. {failed_count} subtasks failed, {timeout_count} timed out."

        # Aggregate based on mode
        if mode == TaskMode.SUBTASKS:
            return self._aggregate_subtasks(completed, original_prompt)
        elif mode == TaskMode.CONSENSUS:
            return self._aggregate_consensus(completed)
        else:  # CONTEXT
            return self._aggregate_context(completed, original_prompt)

    def _aggregate_subtasks(
        self,
        subtasks: list[dict],
        original_prompt: str
    ) -> str:
        """
        Aggregate responses from independent subtasks.

        Creates a structured response combining all parts.
        """
        if len(subtasks) == 1:
            return subtasks[0]["response"]

        # Build structured response
        parts = []

        # Add intro if we can identify the task type
        task_type = self._identify_task_type(original_prompt)
        if task_type:
            parts.append(f"## {task_type}\n")

        # Add each subtask response
        for i, subtask in enumerate(subtasks, 1):
            response = subtask["response"].strip()

            # Try to extract a title from the subtask prompt
            title = self._extract_subtask_title(subtask["prompt"])

            if title:
                parts.append(f"### {title}\n{response}\n")
            else:
                parts.append(f"### Part {i}\n{response}\n")

        return "\n".join(parts)

    def _aggregate_consensus(self, subtasks: list[dict]) -> str:
        """
        Aggregate responses using consensus voting.

        Compares responses and returns the most common/reliable one.
        """
        if len(subtasks) == 1:
            return subtasks[0]["response"]

        responses = [s["response"] for s in subtasks]

        # Simple similarity check: find the response most similar to others
        def similarity_score(response: str, others: list[str]) -> float:
            """Calculate average similarity to other responses."""
            response_words = set(response.lower().split())
            scores = []
            for other in others:
                if other == response:
                    continue
                other_words = set(other.lower().split())
                if not response_words or not other_words:
                    continue
                intersection = len(response_words & other_words)
                union = len(response_words | other_words)
                scores.append(intersection / union if union > 0 else 0)
            return sum(scores) / len(scores) if scores else 0

        # Find response with highest similarity to others
        best_response = responses[0]
        best_score = 0

        for response in responses:
            score = similarity_score(response, responses)
            if score > best_score:
                best_score = score
                best_response = response

        # Check if there's significant disagreement
        if best_score < 0.3 and len(responses) >= 3:
            # Low consensus - return with warning
            return f"**Note: Low consensus among nodes.**\n\n{best_response}"

        return best_response

    def _aggregate_context(
        self,
        subtasks: list[dict],
        original_prompt: str
    ) -> str:
        """
        Aggregate responses from context-split processing.

        Synthesizes partial analyses into a coherent summary.
        """
        if len(subtasks) == 1:
            return subtasks[0]["response"]

        # Sort by section number if present
        def get_section_num(subtask: dict) -> int:
            match = re.search(r'\[Section (\d+)\]', subtask.get("prompt", ""))
            return int(match.group(1)) if match else 0

        sorted_subtasks = sorted(subtasks, key=get_section_num)

        # Build summary
        parts = ["## Analysis Summary\n"]

        for i, subtask in enumerate(sorted_subtasks, 1):
            response = subtask["response"].strip()
            parts.append(f"### Section {i} Analysis\n{response}\n")

        # Add synthesis note
        parts.append("\n---\n*Analysis compiled from multiple document sections.*")

        return "\n".join(parts)

    def _identify_task_type(self, prompt: str) -> Optional[str]:
        """Identify the type of task from the prompt."""
        task_patterns = {
            "Analysis Results": r'\b(analyze|analysis)\b',
            "Extracted Information": r'\b(extract|extraction)\b',
            "Summary": r'\b(summarize|summary)\b',
            "Comparison": r'\b(compare|comparison)\b',
            "Identified Items": r'\b(identify|find|list)\b',
            "Explanation": r'\b(explain|describe)\b',
        }

        for title, pattern in task_patterns.items():
            if re.search(pattern, prompt, re.IGNORECASE):
                return title

        return None

    def _extract_subtask_title(self, prompt: str) -> Optional[str]:
        """Extract a descriptive title from a subtask prompt."""
        # Look for task indicators
        patterns = [
            r'Task:\s*(.+?)(?:\n|$)',  # "Task: X"
            r'(?:extract|identify|find|analyze)\s+(?:the\s+)?(.+?)(?:\.|$)',  # "extract X"
        ]

        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # Capitalize and limit length
                title = title.capitalize()
                if len(title) > 50:
                    title = title[:47] + "..."
                return title

        return None


# Global response aggregator instance
response_aggregator = ResponseAggregator()
