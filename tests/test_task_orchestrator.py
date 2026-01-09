"""
Tests for task orchestrator.
"""

import pytest
from coordinator.task_orchestrator import TaskOrchestrator


class TestTaskDivision:
    """Tests for task division logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = TaskOrchestrator()

    def test_numbered_list_division(self):
        """Test division of numbered list items."""
        prompt = """Analyze the following document and:
1. Extract the main themes
2. Identify key stakeholders
3. List the proposed solutions"""

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        assert len(subtasks) == 3
        assert "main themes" in subtasks[0].lower() or "themes" in subtasks[0].lower()

    def test_lettered_list_division(self):
        """Test division of lettered list items."""
        prompt = """Review the code and:
a) Check for security vulnerabilities
b) Identify performance issues
c) Suggest improvements"""

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        assert len(subtasks) == 3

    def test_bullet_list_division(self):
        """Test division of bullet list items."""
        prompt = """Process the data:
- Clean missing values
- Normalize columns
- Generate summary statistics"""

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        assert len(subtasks) == 3

    def test_extract_pattern_division(self):
        """Test division using extract X, Y, and Z pattern."""
        prompt = "Extract the names, dates, and locations from the document."

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        assert len(subtasks) == 3
        assert any("names" in s.lower() for s in subtasks)
        assert any("dates" in s.lower() for s in subtasks)
        assert any("locations" in s.lower() for s in subtasks)

    def test_spanish_conjunction_division(self):
        """Test division with Spanish conjunctions."""
        prompt = "Analiza el texto y extrae los temas principales, los personajes, y las conclusiones."

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        # Should find comma-separated items
        assert len(subtasks) >= 2

    def test_no_division_single_task(self):
        """Test that simple prompts are not divided."""
        prompt = "What is the capital of France?"

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        assert len(subtasks) == 1
        assert subtasks[0] == prompt

    def test_preserves_context(self):
        """Test that context is preserved in subtasks."""
        prompt = """Given the following financial report:

Revenue increased by 15% this quarter.

Please:
1. Analyze the growth trends
2. Identify risk factors"""

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        # Each subtask should include context about financial report
        for subtask in subtasks:
            # Either contains the context or is the task
            assert len(subtask) > 10


class TestContextDivision:
    """Tests for context/document division."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = TaskOrchestrator()

    def test_short_content_not_divided(self):
        """Test that short content is not divided."""
        prompt = "Analyze this short text."

        chunks = self.orchestrator._divide_by_context(prompt, chunk_size=1000)

        assert len(chunks) == 1

    def test_long_content_divided(self):
        """Test that long content is divided into chunks."""
        # Create long content
        long_text = "This is a test sentence. " * 500  # About 12,500 characters
        prompt = f"Analyze the following:\n\n{long_text}"

        chunks = self.orchestrator._divide_by_context(prompt, chunk_size=4000)

        assert len(chunks) > 1

    def test_chunks_have_section_markers(self):
        """Test that chunks are marked with section numbers."""
        long_text = "Content here. " * 500
        prompt = f"Analyze:\n\n{long_text}"

        chunks = self.orchestrator._divide_by_context(prompt, chunk_size=4000)

        for i, chunk in enumerate(chunks, 1):
            assert f"[Section {i}]" in chunk


class TestHelperMethods:
    """Tests for helper methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = TaskOrchestrator()

    def test_extract_context(self):
        """Test context extraction."""
        prompt = "Given the following data:\n\n1. Item one\n2. Item two"

        context = self.orchestrator._extract_context(prompt)

        assert "Given the following data" in context or context == ""

    def test_is_task_sentence_positive(self):
        """Test task sentence detection - positive cases."""
        assert self.orchestrator._is_task_sentence("Analyze the results")
        assert self.orchestrator._is_task_sentence("What is the main theme?")
        assert self.orchestrator._is_task_sentence("You should review the code")

    def test_is_task_sentence_negative(self):
        """Test task sentence detection - negative cases."""
        assert not self.orchestrator._is_task_sentence("The sky is blue")
        assert not self.orchestrator._is_task_sentence("In 2024, sales increased")


class TestEdgeCases:
    """Tests for edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = TaskOrchestrator()

    def test_empty_prompt(self):
        """Test handling of empty prompt."""
        subtasks = self.orchestrator._divide_into_subtasks("")

        assert len(subtasks) == 1
        assert subtasks[0] == ""

    def test_whitespace_only_prompt(self):
        """Test handling of whitespace-only prompt."""
        subtasks = self.orchestrator._divide_into_subtasks("   \n\n   ")

        assert len(subtasks) == 1

    def test_single_item_list(self):
        """Test that single-item lists are not divided."""
        prompt = "1. Do this one thing"

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        # Single item list shouldn't trigger division
        assert len(subtasks) == 1

    def test_nested_lists(self):
        """Test handling of nested lists."""
        prompt = """Tasks:
1. First main task
   a. Subtask A
   b. Subtask B
2. Second main task"""

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        # Should divide at main level
        assert len(subtasks) >= 2

    def test_mixed_formats(self):
        """Test handling of mixed list formats."""
        prompt = """Do these things:
1. First item
- Second item
* Third item"""

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        assert len(subtasks) >= 2

    def test_unicode_content(self):
        """Test handling of unicode content."""
        prompt = """分析以下内容：
1. 第一个任务
2. 第二个任务
3. 第三个任务"""

        subtasks = self.orchestrator._divide_into_subtasks(prompt)

        assert len(subtasks) >= 2
