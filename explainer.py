import json
import os
from typing import Literal

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

DEPTH_PROMPTS = {
    "beginner": """You are a patient computer science tutor explaining Python code execution 
to someone who has just started learning to program.

Rules:
- Use simple, everyday analogies (e.g., "a variable is like a labeled box")
- Define every technical term the first time you use it
- Explain WHY each line runs and what it accomplishes in the bigger picture
- When a value changes, explain the cause-and-effect chain step by step
- For loops, explain the concept of iteration in simple terms
- For conditionals, explain boolean evaluation simply
- Avoid jargon; when you must use a term, define it in parentheses
- Keep sentences short and clear
- Use phrases like "The computer now..." or "Python checks if..." to make it concrete""",

    "intermediate": """You are a computer science teaching assistant explaining Python execution 
to a student with 1-2 semesters of programming experience.

Rules:
- Use standard CS terminology (variable binding, scope, stack frame, iteration, predicate)
- Explain control flow decisions with reference to expression evaluation
- When values change, state the operation and its semantics precisely
- Mention time complexity or algorithmic implications when relevant
- For function calls, explain the call stack and parameter passing
- For loops, reference the iterator protocol and loop invariants when applicable
- Be concise but thorough — don't over-explain basics, but clarify non-obvious behavior
- Reference Python-specific semantics (e.g., truthiness, short-circuit evaluation) when relevant""",

    "advanced": """You are a senior software engineer conducting a detailed code review 
and execution analysis for an experienced developer.

Rules:
- Use precise PL theory and systems terminology (binding semantics, evaluation order,
  reference semantics, stack discipline, name resolution via LEGB rule)
- Discuss memory model implications (object identity vs equality, reference counting)
- Note performance characteristics (amortized complexity, cache behavior)
- For function calls, discuss activation records and closure semantics if relevant
- For data structures, reference implementation details (e.g., dict as hash table, list as dynamic array)
- Point out subtle Python semantics (late binding, descriptor protocol, MRO)
- Mention potential pitfalls, edge cases, or optimization opportunities
- Be terse and precise — assume deep familiarity with programming concepts""",
}


def _format_trace_for_prompt(trace: dict) -> str:
    lines = []
    lines.append("=== SOURCE CODE ===")
    for i, src_line in enumerate(trace["source_lines"], 1):
        lines.append(f"  {i:3d} | {src_line}")
    lines.append("")
    lines.append("=== EXECUTION TRACE ===")

    for step in trace["steps"]:
        step_num = step["step"]
        event = step["event"]
        lineno = step["line_number"]
        source = step["source_line"]

        lines.append(f"\n--- Step {step_num} [{event}] Line {lineno}: {source} ---")

        changes = step.get("changes", {})
        created = changes.get("created", {})
        updated = changes.get("updated", {})
        deleted = changes.get("deleted", {})

        if created:
            for var, val in created.items():
                lines.append(f"  NEW: {var} = {val['value']} (type: {val['type']})")
        if updated:
            for var, info in updated.items():
                lines.append(f"  CHANGED: {var}: {info['from']['value']} -> {info['to']['value']}")
        if deleted:
            for var, val in deleted.items():
                lines.append(f"  DELETED: {var} (was {val['value']})")

        cf = step.get("control_flow")
        if cf:
            cf_type = cf["type"]
            if cf_type == "function_call":
                lines.append(f"  CONTROL: Calling function '{cf['function']}' (depth: {cf['call_depth']})")
            elif cf_type == "function_return":
                lines.append(f"  CONTROL: Returning from '{cf['function']}' with {cf['return_value']}")
            elif cf_type == "conditional":
                lines.append(f"  CONTROL: Evaluating conditional: {cf['expression']}")
            elif cf_type == "loop":
                lines.append(f"  CONTROL: Loop iteration: {cf['expression']}")
            elif cf_type == "exception":
                lines.append(f"  CONTROL: Exception {cf['exception_type']}: {cf['exception_message']}")

    if trace.get("error"):
        lines.append(f"\n=== EXECUTION ERROR ===")
        lines.append(f"  {trace['error']['type']}: {trace['error']['message']}")

    if trace.get("truncated"):
        lines.append(f"\n[Trace truncated at {trace['step_count']} steps]")

    return "\n".join(lines)


def _build_prompt(trace: dict, depth: str) -> str:
    system = DEPTH_PROMPTS.get(depth, DEPTH_PROMPTS["intermediate"])
    trace_text = _format_trace_for_prompt(trace)

    prompt = f"""{system}

You are given a Python program's source code and its complete execution trace.
Your task is to generate a natural-language explanation for each execution step.

IMPORTANT RULES:
1. Do NOT restate the source code verbatim. Explain what is happening and WHY.
2. Explain why values change — trace the cause back to the operation.
3. Explain why branches are taken — what condition evaluated to what.
4. Group related steps (e.g., loop iterations) when it aids clarity.
5. If there's an error, explain why it occurred and what would fix it.

{trace_text}

Respond with a JSON object in this exact format:
{{
  "summary": "A 1-3 sentence overview of what this code does and its key algorithmic idea",
  "step_explanations": [
    {{
      "step": <step_number>,
      "line": <line_number>,
      "explanation": "Your natural language explanation of this step"
    }}
  ],
  "key_concepts": ["list", "of", "CS concepts", "demonstrated by this code"]
}}

Return ONLY valid JSON, no markdown formatting or code fences."""

    return prompt


def explain_trace(
    trace: dict,
    depth: Literal["beginner", "intermediate", "advanced"] = "intermediate",
) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not set. Add it to your .env file or environment."
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = _build_prompt(trace, depth)

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )

        response_text = response.text.strip()

        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)

        if "summary" not in result or "step_explanations" not in result:
            raise RuntimeError("LLM response missing required fields")

        result["depth"] = depth
        result["model"] = "gemini-2.0-flash"
        return result

    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse LLM response as JSON: {e}")
    except Exception as e:
        if "json" in str(type(e).__name__).lower():
            raise
        raise RuntimeError(f"Gemini API error: {e}")


def get_example_prompt(trace: dict, depth: str = "intermediate") -> str:
    return _build_prompt(trace, depth)
