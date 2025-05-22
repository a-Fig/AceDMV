from dotenv import load_dotenv
import os
from google.cloud import texttospeech

load_dotenv()


def remove_non_ascii(s):
    s = ''.join(c for c in s if ord(c) < 256)
    bad_characters = ["*", "\\", "'", "\"", "`"]
    for char in bad_characters:
        s = s.replace(char, '')
    return s


def text_to_speech_premium(text, voice_model="en-US-Chirp3-HD-Fenrir"):
    # Set the path to your service account key file
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_JSON_KEY")
    # Initialize the client
    client = texttospeech.TextToSpeechClient()

    text = remove_non_ascii(text)

    # Set the text input
    synthesis_input = texttospeech.SynthesisInput(text=text)

    # Configure voice parameters - using a premium voice (Wavenet)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name=voice_model # Example: Using Wavenet voice D for US English
    )

    # Set audio configuration
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    # Generate speech
    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )

    return response.audio_content


if __name__ == '__main__':
    pass
