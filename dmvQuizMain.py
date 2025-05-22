from typing import List, TypedDict, Callable, Tuple
import questionclass as mcq
import questionlist

import Tutorllm

print("dmvQuizMain.py")

# fix pause button for voice
# use better voice


if __name__ == '__main__':
    try:
        score: int = 0
        questions_answered: int = 0
        while True:
            question: mcq.Question = questionlist.pick_question()
            full_question = f"\n{question.build_question()}"
            print(full_question)

            questions_answered += 1

            user_message = input("enter choice>")
            if user_message == "stop":
                break

            grade, reason = question.grade_answer(user_message)
            if grade > 0.80:
                score += 1
                print(f"{score}/{questions_answered} - Correct! ",end='')
                if reason != "":
                    print(f"{grade * 100}% , {reason}", end='')
                print()
            else:
                print(f"{score}/{questions_answered} - Incorrect, entering chat with AI, type 'next' to move on to the next question")
                grader_response = f"Grader justification: {reason}" if reason != "" else ""
                Tutorllm.Tutor.prompt(f""" The user has answered a question incorrectly.
                Original Question: {full_question}
                Student's Incorrect Answer: {user_message}
                Question Explanation: {question.explanation}
                {grader_response}
                Send them a message to help them understand.
                """)
                user_message = input("respond>")
                while user_message != "next":
                    Tutorllm.Tutor.prompt(f"user response: '{user_message}'")
                    user_message = input("respond>")

    except Exception as e:
        print(f"Exception: {e}")

    print(Tutorllm.Tutor.llm.chat_history(user_label="input>", model_label="gemini>"))

