# Privacy and data flow

Continuous visual processing runs locally. Only the stuck word and its sentence go to the cloud.

| Data | Where it goes | When |
|---|---|---|
| Camera or screen frames | Stay in memory on this computer. Never written to disk, never uploaded. | Always |
| OCR text of the whole page | Stays on this computer (and is shown in the local UI). | Always |
| `word` (one token, max 64 characters) and `context` (the containing sentence, max 600 characters) | HTTPS POST to your API Gateway `/assist` | Only after the dwell engine reports STUCK_WORD and the state machine allows a request |
| Generated definition and MP3 | Returned to this computer, kept in memory for replay | After a request |

* The Lambda logs lengths, timings and a request id. It does not log the word, the sentence or the definition.
* Bedrock and Polly receive the word, sentence and the generated definition, as required to do the work.
* The local agent holds no AWS credentials. It sends an optional API key header that identifies the app to API Gateway.
* The local API listens on 127.0.0.1 and rejects browser requests from origins other than the UI.
* The agent never stores reading content. `/api/state` keeps the last request payload in memory so the Privacy view can show exactly what was sent.
* Screen mode captures everything inside the chosen monitor or region. Use a region or a second monitor so other windows are not read.
