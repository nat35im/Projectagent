
import speech_recognition as sr
import pyttsx3
import google.generativeai as genai

model = pyttsx3.init()
genai.configure(api_key="test")
m = genai.GenerativeModel("gemini-1.5-flash")

with sr.Microphone() as source:
    sr.Recognizer().adjust_for_ambient_noise(source,duration=2)
    print("Waiting.......")
    model.say("How can I help you")
    model.runAndWait()
    au = sr.Recognizer().listen(source, timeout=5, phrase_time_limit=10)
try:
    q = sr.Recognizer().recognize_google(au)
    q1 = "You said :………………. "+ q + "………………….Please wait for a few seconds…….. "
    model.say(q1)
    model.runAndWait()
    print(q1)
    r = m.generate_content(q)
    model.say(r.text)
    print(r.text)
    model.runAndWait()
    print("Please retry")
except:
    pass