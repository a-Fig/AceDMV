# python -m uvicorn fastapi_test:app --reload
# http://127.0.0.1:8000

import uuid
from fastapi import FastAPI, HTTPException, Request, Body, Depends
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Tuple, Optional, Dict, Any

# --- Session Management ---
from starlette.middleware.sessions import SessionMiddleware

# --- Google Cloud Text-to-Speech ---
from google.cloud import texttospeech

# --- Existing Quiz Logic Imports ---
import questionclass as mcq
import questionlist
import modifiedTutorllm as Tutorllm
import chatapi

import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_JSON_FILE_KEY = os.getenv("GOOGLE_JSON_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_CLIENT_API_KEY")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")

PRINT_DEBUG = False  # Enable for detailed logging
# --- FastAPI App Setup ---
app = FastAPI()

# --- Session Middleware Configuration ---
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)

# --- Google Cloud TTS Configuration ---
SERVICE_ACCOUNT_KEY_FILE_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
TTS_SERVICE_ENABLED = False
tts_client = None

if SERVICE_ACCOUNT_KEY_FILE_PATH and os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
    try:
        tts_client = texttospeech.TextToSpeechClient()
        TTS_SERVICE_ENABLED = True
        if PRINT_DEBUG: print(
            f"DEBUG: Google Cloud TextToSpeechClient initialized via GOOGLE_APPLICATION_CREDENTIALS: {SERVICE_ACCOUNT_KEY_FILE_PATH}.")
    except Exception as e:
        if PRINT_DEBUG: print(
            f"DEBUG: ERROR: Could not initialize TextToSpeechClient via GOOGLE_APPLICATION_CREDENTIALS: {e}")
else:
    LOCAL_SERVICE_ACCOUNT_KEY_FILE = GOOGLE_JSON_FILE_KEY
    if os.path.exists(LOCAL_SERVICE_ACCOUNT_KEY_FILE):
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = LOCAL_SERVICE_ACCOUNT_KEY_FILE
            tts_client = texttospeech.TextToSpeechClient()
            TTS_SERVICE_ENABLED = True
            if PRINT_DEBUG: print(
                f"DEBUG: Google Cloud TextToSpeechClient initialized using local key file: {LOCAL_SERVICE_ACCOUNT_KEY_FILE}.")
        except Exception as e:
            if PRINT_DEBUG: print(
                f"DEBUG: ERROR: Could not initialize TextToSpeechClient using local key file '{LOCAL_SERVICE_ACCOUNT_KEY_FILE}': {e}")
    else:
        if PRINT_DEBUG: print(
            f"DEBUG: WARNING: TTS Service Account Key file not found (checked env var and local path: '{LOCAL_SERVICE_ACCOUNT_KEY_FILE}'). TTS will be disabled.")


def remove_non_ascii(s):
    s = ''.join(c for c in s if ord(c) < 256)
    bad_characters = ["*", "\\", "`"]
    for char in bad_characters:
        s = s.replace(char, '')
    s= s.replace("\n", ".\n")
    return s

def generate_speech_audio(text_to_speak: str) -> Optional[bytes]:
    text_to_speak = remove_non_ascii(text_to_speak)
    if not TTS_SERVICE_ENABLED or not tts_client:
        print("TTS client not available. Cannot generate speech.")
        return None
    try:
        synthesis_input = texttospeech.SynthesisInput(text=text_to_speak)
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Chirp3-HD-Fenrir")
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        return response.audio_content
    except Exception as e:
        print(f"Error during TTS synthesis: {e}")
        return None


templates_path = os.path.join(os.path.dirname(__file__), "templates")
if not os.path.exists(templates_path):
    os.makedirs(templates_path, exist_ok=True)
    index_html_path = os.path.join(templates_path, "index.html")
    if not os.path.exists(index_html_path):
        with open(index_html_path, "w") as f:
            f.write("<h1>DMV Quiz (Template Placeholder)</h1><p>If you see this, your index.html is missing.</p>")
templates = Jinja2Templates(directory=templates_path)


class AnswerRequest(BaseModel):
    answer: str


class ChatRequest(BaseModel):
    message: str


class TTSRequest(BaseModel):
    text: str


def initialize_session_state(session: dict):
    if PRINT_DEBUG: print(f"DEBUG: Initializing session state for session: {session.get('session_id_debug', 'N/A')}")
    session["score"] = 0
    session["questions_answered"] = 0
    session["current_question_cat_idx"] = None  # Store category index
    session["current_question_q_idx"] = None  # Store question index within category
    session["_messages_for_ui_capture"] = []
    session["active_quiz"] = True
    if 'session_id_debug' not in session:
        session['session_id_debug'] = str(uuid.uuid4())
    if PRINT_DEBUG: print(
        f"DEBUG: Session state initialized. ID: {session['session_id_debug']}, Active: {session['active_quiz']}")


def patched_send_message_for_session(messages: List[str], session_message_capture_list: List[str]) -> Tuple[bool, str]:
    if not messages:
        return True, "Error: No messages to send."
    full_message = "\n".join(messages)
    session_message_capture_list.append(full_message)
    return False, "Message successfully prepared for UI via patched function"


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    if PRINT_DEBUG: print(f"DEBUG: GET / - Request cookies: {request.cookies}")
    if "active_quiz" not in request.session:
        initialize_session_state(request.session)
    if PRINT_DEBUG: print(f"DEBUG: GET / - Session after init check: {dict(request.session)}")
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/get-question", response_class=JSONResponse)
async def get_question_api(request: Request):
    session = request.session
    if PRINT_DEBUG: print(f"DEBUG: GET /api/get-question - Session at entry: {dict(session)}")

    if not session.get("active_quiz", False):
        if PRINT_DEBUG: print(
            "DEBUG: GET /api/get-question - No active quiz or first load, re-initializing session state.")
        initialize_session_state(session)

    # Use the new pick_question to get indices
    try:
        cat_idx, q_idx = questionlist.pick_question()
        question_obj: mcq.Question = questionlist.get_question(cat_idx, q_idx)
    except IndexError:  # If indices are out of range for some reason
        session["active_quiz"] = False
        if PRINT_DEBUG: print(f"DEBUG: GET /api/get-question - IndexError while getting question. Ending quiz.")
        return JSONResponse(content={
            "error": "Error fetching question (index out of range). Quiz ended.", "quiz_ended": True,
            "score": session.get("score", 0), "questions_answered": session.get("questions_answered", 0)
        })
    except AttributeError:  # If pick_question or get_question are not found in questionlist
        session["active_quiz"] = False
        if PRINT_DEBUG: print(
            f"DEBUG: GET /api/get-question - AttributeError: pick_question or get_question not found in questionlist.py. Ending quiz.")
        return JSONResponse(content={
            "error": "Server configuration error (question retrieval). Quiz ended.", "quiz_ended": True,
            "score": session.get("score", 0), "questions_answered": session.get("questions_answered", 0)
        })

    if not question_obj:  # Should be caught by IndexError if list is empty or indices wrong
        session["active_quiz"] = False
        if PRINT_DEBUG: print(f"DEBUG: GET /api/get-question - No question object returned. Session: {dict(session)}")
        return JSONResponse(content={
            "error": "No more questions available.", "quiz_ended": True,
            "score": session.get("score", 0), "questions_answered": session.get("questions_answered", 0)
        })

    # Store indices in session
    session["current_question_cat_idx"] = cat_idx
    session["current_question_q_idx"] = q_idx

    # No need to strip .grader as we are not pickling the object in session anymore.
    # The object is live for this request, then retrieved fresh using indices for the next.

    question_text_full_for_ai = question_obj.build_question()  # Populates last_option_set for MCQs

    # --- Prepare data for frontend ---
    question_stem_for_display = question_obj.question
    options_for_display = []
    question_type_for_frontend = ""

    if isinstance(question_obj, mcq.MultipleChoice):
        question_type_for_frontend = "mcq"
        options_for_display = question_obj.last_option_set
    elif isinstance(question_obj, mcq.ShortAnswer):
        question_type_for_frontend = "short_answer"
    else:
        if PRINT_DEBUG: print(f"ERROR: Unknown question type: {type(question_obj)}")
        # This case should ideally not be reached if questionlist.py is correctly structured
        raise HTTPException(status_code=500, detail="Unknown question type generated.")

    if PRINT_DEBUG: print(
        f"DEBUG: GET /api/get-question - Storing indices ({cat_idx}, {q_idx}). Frontend type: {question_type_for_frontend}")

    return JSONResponse(content={
        "question": question_stem_for_display,
        "question_full_text_for_ai": question_text_full_for_ai,
        "question_type": question_type_for_frontend,
        "options": options_for_display,
        "score": session.get("score", 0),
        "questions_answered": session.get("questions_answered", 0),
        "explanation_preview": question_obj.explanation[:150] + "..." if question_obj.explanation else ""
    })


@app.post("/api/submit-answer", response_class=JSONResponse)
async def submit_answer_api(request: Request, answer_request: AnswerRequest):
    session = request.session
    if PRINT_DEBUG: print(f"DEBUG: POST /api/submit-answer - Session at entry: {dict(session)}")

    cat_idx = session.get("current_question_cat_idx")
    q_idx = session.get("current_question_q_idx")

    if cat_idx is None or q_idx is None:
        if PRINT_DEBUG: print("DEBUG: POST /api/submit-answer - ERROR: No current_question indices found in session.")
        raise HTTPException(status_code=400, detail="No active question indices in session. Please get a new question.")

    try:
        question_obj: mcq.Question = questionlist.get_question(cat_idx, q_idx)
    except IndexError:
        if PRINT_DEBUG: print(
            f"DEBUG: POST /api/submit-answer - ERROR: IndexError retrieving question with indices ({cat_idx}, {q_idx}).")
        raise HTTPException(status_code=400, detail="Error retrieving current question. Please get a new question.")
    except AttributeError:
        if PRINT_DEBUG: print(
            f"DEBUG: POST /api/submit-answer - ERROR: AttributeError, get_question not found in questionlist.py.")
        raise HTTPException(status_code=500, detail="Server configuration error (question retrieval).")

    if not question_obj:  # Should be caught by IndexError if list is empty or indices wrong
        if PRINT_DEBUG: print(
            f"DEBUG: POST /api/submit-answer - ERROR: No question object returned for indices ({cat_idx}, {q_idx}).")
        raise HTTPException(status_code=400, detail="No active question object for indices. Please get a new question.")

    if PRINT_DEBUG: print(
        f"DEBUG: /submit-answer - Retrieved question object of type: {type(question_obj)}, text: {question_obj.question[:30]} using indices ({cat_idx}, {q_idx})")
    if PRINT_DEBUG: print(f"DEBUG: /submit-answer - Received answer from frontend: {answer_request.answer}")

    user_answer_str = answer_request.answer
    grade = 0.0
    reason_str = ""
    is_correct = False
    ai_messages_for_response = []

    try:
        if isinstance(question_obj, mcq.ShortAnswer):
            question_obj.setup_grader()  # Reinitialize FlashChat grader if it was ever stripped or not set
            if PRINT_DEBUG: print(f"DEBUG: /submit-answer - Called setup_grader() for ShortAnswer.")


        if PRINT_DEBUG: print(
            f"DEBUG: Calling {type(question_obj).__name__}.grade_answer() with answer: '{user_answer_str}'")
        grade_val, reason_str_from_method = question_obj.grade_answer(user_answer_str)
        grade = float(grade_val)
        reason_str = reason_str_from_method
        is_correct = grade > 0.80
    except Exception as e:
        if PRINT_DEBUG: print(f"DEBUG: /submit-answer - Error during grading: {e}")
        reason_str = f"Grading error: {str(e)}"

    session["questions_answered"] = session.get("questions_answered", 0) + 1
    if is_correct:
        session["score"] = session.get("score", 0) + 1

    if PRINT_DEBUG: print(
        f"DEBUG: POST /api/submit-answer - Answer graded. Correct: {is_correct}, Score: {session['score']}/{session['questions_answered']}, Reason: {reason_str}")

    # --- AI Tutor Interaction ---
    session_ui_capture_list = session.get("_messages_for_ui_capture", [])
    session_ui_capture_list.clear()

    original_send_message_action = None
    if hasattr(Tutorllm, 'Tutor') and "send_message" in Tutorllm.Tutor.tools:
        original_send_message_action = Tutorllm.Tutor.tools["send_message"].action
        Tutorllm.Tutor.tools["send_message"].action = lambda msgs: patched_send_message_for_session(msgs,
                                                                                                    session_ui_capture_list)
    else:
        if PRINT_DEBUG: print("WARNING: Tutor or send_message tool not found for patching.")

    try:
        full_question_text_for_ai = question_obj.rebuild_question()

        if is_correct:
            tutor_prompt_text = f"""The user answered correctly.
Original Question: {full_question_text_for_ai}
User's Answer: {user_answer_str}
Question Explanation: {question_obj.explanation}
Grader's Reason for Correct (if any): {reason_str if reason_str else ""}
Offer brief reinforcement or additional context, and ask if they are ready for the next question. Keep it short as they got the question right"""
        else:
            grader_response_text_for_tutor = f"Grader justification: {reason_str}" if reason_str else "The answer was not satisfactory."
            tutor_prompt_text = f"""The user has answered a question incorrectly.
Original Question: {full_question_text_for_ai}
Student's Incorrect Answer: {user_answer_str}
Question Explanation: {question_obj.explanation}
{grader_response_text_for_tutor}
Send them a message to help them understand. Focus on the specific errors or omissions based on the grader's justification."""

        if hasattr(Tutorllm, 'Tutor'):
            Tutorllm.Tutor.prompt(tutor_prompt_text)
            ai_messages_for_response.extend(session_ui_capture_list)
        else:
            ai_messages_for_response.append("AI Tutor is currently unavailable.")

    except Exception as e:
        if PRINT_DEBUG: print(f"DEBUG: Error during Tutorllm.Tutor.prompt (submit answer): {e}")
        ai_messages_for_response.append("Tutor error. Please try again or proceed to the next question.")
    finally:
        if original_send_message_action and hasattr(Tutorllm, 'Tutor') and "send_message" in Tutorllm.Tutor.tools:
            Tutorllm.Tutor.tools["send_message"].action = original_send_message_action
        session["_messages_for_ui_capture"] = list(session_ui_capture_list)

    if PRINT_DEBUG: print(
        f"DEBUG: POST /api/submit-answer - Returning response. AI messages count: {len(ai_messages_for_response)}")
    return JSONResponse(content={
        "correct": is_correct, "grade": grade, "reason": reason_str,
        "score": session.get("score", 0), "questions_answered": session.get("questions_answered", 0),
        "ai_messages": ai_messages_for_response,
        "explanation": question_obj.explanation
    })


@app.post("/api/chat-with-tutor", response_class=JSONResponse)
async def chat_with_tutor_api(request: Request, chat_request: ChatRequest):
    session = request.session
    if PRINT_DEBUG: print(f"DEBUG: POST /api/chat-with-tutor - Session at entry: {dict(session)}")

    cat_idx = session.get("current_question_cat_idx")
    q_idx = session.get("current_question_q_idx")

    if cat_idx is None or q_idx is None:  # Check if there are active question indices
        if PRINT_DEBUG: print(
            "DEBUG: POST /api/chat-with-tutor - ERROR: No current_question indices for tutor chat context.")
        raise HTTPException(status_code=400, detail="Tutor chat not active or no question context.")

    user_message = chat_request.message
    ai_response_messages = []
    session_ui_capture_list = session.get("_messages_for_ui_capture", [])
    session_ui_capture_list.clear()

    if user_message.lower().strip() == "next":
        return JSONResponse(content={"ai_messages": ["Okay, let's move to the next question!"], "move_next": True})

    original_send_message_action = None
    if hasattr(Tutorllm, 'Tutor') and "send_message" in Tutorllm.Tutor.tools:
        original_send_message_action = Tutorllm.Tutor.tools["send_message"].action
        Tutorllm.Tutor.tools["send_message"].action = lambda msgs: patched_send_message_for_session(msgs,
                                                                                                    session_ui_capture_list)
    else:
        if PRINT_DEBUG: print("WARNING: Tutor or send_message tool not found for patching in chat.")

    try:
        tutor_prompt = f"User follow-up message: '{user_message}'"
        if hasattr(Tutorllm, 'Tutor'):
            Tutorllm.Tutor.prompt(tutor_prompt)
            ai_response_messages.extend(session_ui_capture_list)
        else:
            ai_response_messages.append("AI Tutor is currently unavailable for chat.")
    except Exception as e:
        if PRINT_DEBUG: print(f"DEBUG: Error during Tutorllm.Tutor.prompt (chat): {e}")
        ai_response_messages.append("I had a problem processing that. Can you try rephrasing?")
    finally:
        if original_send_message_action and hasattr(Tutorllm, 'Tutor') and "send_message" in Tutorllm.Tutor.tools:
            Tutorllm.Tutor.tools["send_message"].action = original_send_message_action
        session["_messages_for_ui_capture"] = list(session_ui_capture_list)

    if PRINT_DEBUG: print(
        f"DEBUG: POST /api/chat-with-tutor - Returning AI messages count: {len(ai_response_messages)}")
    return JSONResponse(content={"ai_messages": ai_response_messages, "move_next": False})


@app.post("/api/tts")
async def text_to_speech_endpoint(tts_request: TTSRequest):
    if not TTS_SERVICE_ENABLED or not tts_client:
        raise HTTPException(status_code=503, detail="Text-to-Speech service is not available.")
    audio_content = generate_speech_audio(tts_request.text)
    if audio_content:
        return Response(content=audio_content, media_type="audio/mpeg")
    else:
        raise HTTPException(status_code=500, detail="Failed to generate speech.")


if __name__ == "__main__":
    import uvicorn

    print("Starting FastAPI server for DMV Quiz...")
    gemini_api_key_present = hasattr(chatapi,
                                     'GEMINI_API_KEY') and chatapi.GEMINI_API_KEY and chatapi.GEMINI_API_KEY not in [
                                 "YOUR_AI_STUDIO_API_KEY_HERE", GEMINI_API_KEY]
    if not gemini_api_key_present:
        print("\nCRITICAL WARNING: GEMINI_API_KEY is not set or is a placeholder in chatapi.py.")
    else:
        if PRINT_DEBUG: print("DEBUG: Gemini API Key found in chatapi.py.")
    if not TTS_SERVICE_ENABLED:
        if PRINT_DEBUG: print("\nDEBUG: WARNING: TTS client failed to initialize or is disabled.")
    else:
        if PRINT_DEBUG: print("DEBUG: TTS Service is ENABLED.")
    if SESSION_SECRET_KEY == "your-super-secret-key-please-change123":
        print("WARNING: Using default SESSION_SECRET_KEY. This is insecure for production.")
    uvicorn.run(app, host="0.0.0.0", port=8000)
