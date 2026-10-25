# Demo script (about 3 minutes)

Setup: `python -m local_agent.main`, open http://127.0.0.1:8765, deploy the backend first if you want real AWS (see backend/README.md) and set `ASSIST_API_URL` in `.env`.

1. Dashboard: show the status label READY, input = Demo simulation, cloud = AWS (or MOCK if offline). Say plainly that the demo page is simulated and that detection and OCR run on its real pixels.
2. Start. Open Live Assistant. Point out the detector and OCR names in Diagnostics.
3. Click Run guided demo. Only the pointer movement is scripted. Watch FOCUS DETECTED, the dwell bar, ANALYZING, ASSISTANCE READY.
4. Show the highlighted word and explanation on the frame, play the audio, then Diagnostics: API round trip, Lambda, Bedrock, Polly and total latency.
5. Privacy view: show the exact payload that left the computer (word and sentence only).
6. Live proof: switch to Screen or Camera, open a real page, hold the pointer on a hard word (or use Next word and wait 1.5 s).
7. Failure path: stop the network, trigger a word, show the ERROR label with a plain message and automatic recovery to READING.
