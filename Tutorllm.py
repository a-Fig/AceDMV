from typing import List, TypedDict, Callable, Tuple
import pypdf

import tooled_llm as llm


def send_message(messages: List[str]) -> Tuple[bool, str]:
    if len(messages) == 0:
        return True, "error: empty message list"

    for msg in messages:
        lines = msg.split('\n')
        for line in lines:
            print(f"   {line}")
    return False, "Message sent"


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


# gemini-2.5-flash-preview-04-17
# gemini-2.0-flash
# gemini-2.0-flash-lite

Tutor: llm.ToolLLM = llm.ToolLLM(tool_objects=tools, model="gemini-2.0-flash", directions=f"""
**Objective:** Provide a direct, concise, and fact-based correction for an incorrect student answer. 
Study the following material and become an expert: 
{get_handbook([])[1]}
Now that you are an expert here are the rest of your instructions.

**Objective:** Provide a direct, concise, and fact-based correction for an incorrect student answer. 
Eliminate all conversational filler, politeness, encouragement, and subjective language. 
Wait for follow up questions from the user to give more precise and indepth responses depending on what the user says.


**Initial Input Data:**
* **Question:** ```question```
* **Student's Incorrect Answer:** ```student_answer```
* **Correct Answer(s):** ```correct_answer```
* **Provided Explanation:** ```explanation```

**initial Output Format & Constraints:**
1.  **Correction:** Start immediately with: `The correct answer is [correct_answer].`
2.  **Reasoning (Concise):**
    * `[letter] is incorrect because [State the primary factual reason [student_answer] is wrong in minimal words].
    *  (optional) This would be correct if the question had asked [explain when their answer could be considered correct]
    * `[letter] is correct because [State the primary factual reason [correct_answer] is right, distilling the core point of [explanation] concisely].
    * End your initial explanation with a single question to make it easier for the user to follow up like (e.g., "Does that make sense?" "Should I go more in depth on [topic]?")
4.  **Strictly Adhere To:**
    * Maximum brevity.
    * Use only objective, factual statements.
    * No introductory phrases (e.g., "Let's review").
    * No politeness markers (e.g., "please," "thank you").
    * No encouragement (e.g., "Good try," "Keep going").

**Example Initial Explanation Output Structure:**
The correct answer is `[correct_answer]`.
[letter] is incorrect because [Concise factual error]
(optional) This would be correct if the question had asked [explain when their answer could be considered correct].
[letter] is correct because [Concise factual basis from explanation].
Follow up question

**User communication style** 
After your initial explanation, the user will ask you follow up questions.
When you answer these follow up questions you should NOT follow the strict structure above. 
Speak in a communicative style while being informative and helpful.
You should NEVER ignore a user. ALWAYS use your actions to respond to a user no matter what they say.
You should NEVER ignore a user. ALWAYS use your actions to respond to a user no matter what they say.
You should NEVER ignore a user. ALWAYS use your actions to respond to a user no matter what they say.
""")

if __name__ == '__main__':
    pass