from typing import List, TypedDict, Callable, Tuple
import pypdf
import tooled_llm as llm

import prompt_options


# This global list will be used by the FastAPI app to capture messages.
# It's a bit of a workaround for the existing structure.
# In main.py, we'll clear this list before each Tutor.prompt call and read from it after.
# This is ALREADY HANDLED by the modified_send_message in main.py,
# so this global here is not strictly necessary if main.py does the capture.
# However, the `modified_send_message` in `main.py` uses its own capture list.
# The original `send_message` below can remain as is, or be simplified if
# we are sure the patch in main.py always works.
# For robustness, let's assume the patch in main.py is the primary mechanism.

# Original send_message - will be replaced by `modified_send_message` from main.py at runtime
def send_message(messages: List[str]) -> Tuple[bool, str]:
    if len(messages) == 0:
        return True, "error: empty message list"

    # This print will go to the console where FastAPI server is running
    # It's useful for backend debugging.
    print("--- Original send_message called (should be patched by main.py) ---")
    for msg in messages:
        lines = msg.split('\n')
        for line in lines:
            print(f"   AI (orig): {line}")
    # This return value (False, "Message sent") means the LLM in tooled_llm.py
    # will consider this message "unimportant" and queue it.
    # The patched version in main.py returns True and the actual message content
    # to make it "urgent" and directly usable.
    return False, "Message sent (original function)"


def get_handbook(arg: List[str]) -> Tuple[bool, str]:
    pdf_file_path = "DL600CaliforniaHandbook.pdf"
    doc = pypdf.PdfReader(pdf_file_path)
    extracted_text = ""
    for page_num in range(len(doc.pages)):
        page = doc.pages[page_num].extract_text()
        extracted_text += f"-- Page {page_num + 1} --\n{page}\n\n"
    doc.close()
    return True, extracted_text


tools: List[llm.Toolwrapper] = [
    llm.Toolwrapper("send_message", send_message, """
    Action name: "send_message"
    Arguments: list of messages
    Purpose: Sends 1 or more message to the user. Break up long messages with '\\n'. This is the only way you are able to communicate with users
    Returns: conformation with Success or Fail
    """),
    llm.Toolwrapper("get_handbook", get_handbook, """
    Action name: "get_handbook"
    Arguments: empty list
    Purpose: Use to scan the California Drivers Handbook for any information you need to look for.
    Returns: a copy of the 2025 California Drivers Handbook
    """)
]


# Initial handbook content for the Tutor's prompt
# This will call get_handbook() when Tutorllm.py is imported.
initial_handbook_content, _ = get_handbook([])

Tutor: llm.ToolLLM = llm.ToolLLM(tool_objects=tools, model="gemini-2.0-flash", directions=prompt_options.clear_tutor_propmt)

if __name__ == '__main__':
    # Test the handbook loading
    print("Testing Tutorllm.py standalone...")
    status, handbook_content = get_handbook([])
    print(f"Handbook loaded (status: {status}): {handbook_content}...")

    # Example of how Tutor might be used (won't run full LLM interaction here)
    # print("\nSimulating Tutor prompt (no actual LLM call):")
    # Tutor.llm.history.append({"role": "user", "parts": [{"text": "Initial instructions received."}]}) # Mock history
    # test_prompt_text = "The user answered 'X' to question 'Y'. Explanation is 'Z'. Help them."
    # print(f"Sending to Tutor.prompt (simulation): {test_prompt_text}")
    # This would normally call the LLM:
    # Tutor.prompt(test_prompt_text)

    print("Tutorllm.py initialized.")

