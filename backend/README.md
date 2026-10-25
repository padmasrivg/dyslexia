# AWS backend

`POST /assist` on API Gateway (REST, API key required) -> Lambda (Python 3.13, arm64, boto3 only)
-> Amazon Bedrock Converse (one-sentence explanation) -> Amazon Polly (MP3) -> JSON with Base64 audio.

Files: `lambda_handler.py` (function), `template.yaml` (SAM), `local_server.py` (dev only wrapper).

## Prerequisites

AWS CLI and AWS SAM CLI configured with credentials that may create IAM roles, Lambda, API Gateway and
CloudWatch resources. Pick a region where your chosen Bedrock model and Polly are available.

## 1. Choose and enable a Bedrock model

No model id is hard-coded; models are retired over time. List what your region offers:

```bash
aws bedrock list-foundation-models --region us-east-1 --by-provider anthropic \
  --query "modelSummaries[].[modelId,modelLifecycle.status]" --output table
aws bedrock list-inference-profiles --region us-east-1 \
  --query "inferenceProfileSummaries[].[inferenceProfileId,inferenceProfileArn]" --output table
```

Some models can only be invoked through an inference profile id (prefixed e.g. `us.` or `eu.`). Use that
id as `BedrockModelId`. Enable access to the model in the Bedrock console (Model access) if your account
requires it. Then build `BedrockModelArns`, exact ARNs with no wildcard:

* foundation model id: `arn:aws:bedrock:REGION::foundation-model/MODEL_ID`
* inference profile: the profile ARN **and** the foundation-model ARN of each region it can route to
  (`aws bedrock get-inference-profile --inference-profile-identifier PROFILE_ID`, see `models`).

## 2. Check the Polly voice and engine

```bash
aws polly describe-voices --engine neural --language-code en-US --query "Voices[].Id"
```

Default is voice `Joanna`, engine `neural`. If the engine is rejected or fails, the function retries once
with `POLLY_FALLBACK_ENGINE` (`standard`). If audio still fails, the response is HTTP 200 with
`status: "partial"`, `audio: null` and `warnings: ["audio_unavailable"]`; the text is still returned.

## 3. Deploy

```bash
cd backend
sam build
sam deploy --guided
```

At the prompts supply `BedrockModelId`, `BedrockModelArns` (comma separated), and optionally
`PollyVoiceId`, `PollyEngine`, `AllowedOrigin`, `LogRetentionDays`, `ThrottleRateLimit`,
`ThrottleBurstLimit`. Template lint: `cfn-lint backend/template.yaml`.

## 4. Get the URL and API key, configure the local agent

```bash
aws cloudformation describe-stacks --stack-name STACK \
  --query "Stacks[0].Outputs" --output table          # AssistUrl and ApiKeyId
aws apigateway get-api-key --api-key API_KEY_ID --include-value --query value --output text
export ASSIST_API_URL="https://<id>.execute-api.<region>.amazonaws.com/prod/assist"
export ASSIST_API_KEY="<value printed above>"
```

Treat the key like a password; it is not committed anywhere. Rotate it by replacing the key in the console.

## 5. Test with curl

```bash
curl -sS -X POST "$ASSIST_API_URL" -H "x-api-key: $ASSIST_API_KEY" -H "Content-Type: application/json" \
  -d '{"word":"photosynthesis","context":"Plants use photosynthesis to make food from sunlight."}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); d['audio']=(d['audio'] or '')[:20]+'...'; print(json.dumps(d,indent=2))"
```

Expected: `status` `success`, a one-sentence `definition`, Base64 MP3 `audio`, and `timings`
(`bedrock_ms`, `polly_ms`, `lambda_ms`, measured inside the Lambda). Live check:
`python3 -m pytest tests/integration/test_live_aws.py -q` (skipped unless `ASSIST_API_URL` is set).

## Errors

`{"status":"error","error":{"code","message"}}`. Codes: `invalid_payload`, `empty_word`, `invalid_word`,
`empty_context`, `context_too_long` (400); `payload_too_large` (413, body over 4 KB); `service_busy` (429);
`model_unavailable`, `bedrock_error`, `bedrock_bad_output` (502); `upstream_timeout` (504);
`service_misconfigured`, `internal_error` (500). AWS error text is never returned to the client.
API Gateway itself answers 400 (request model), 403 (missing or wrong key) or 429 (usage plan) with its own
`{"message": ...}` body before the Lambda runs.

## What is and is not logged

The word and sentence come from OCR of whatever the child is reading, so they are treated as private and
as untrusted. Logged (one JSON line per request): request id, status, error code, HTTP status, timings,
the **lengths** of word and context, AWS error codes and AWS request ids. **Never** logged: the word, the
context, the definition, the audio, or AWS error message text. API Gateway access logging is not enabled
by this template (it needs an account-wide CloudWatch role); method metrics are. Logs are kept for
`LogRetentionDays`. Bedrock model invocation logging is an account-level setting you control separately;
if you enable it, prompts are stored by that feature.

Prompt safety: the word and sentence are placed inside `<word>` / `<sentence>` tags with `<` and `>`
escaped, and the system prompt tells the model to treat them as data. This reduces prompt injection risk;
it cannot guarantee it. The output is limited to one sentence (capped at 240 characters) and returned as
text only.

## Local development

`python3 -m backend.local_server` (from the project root) serves the handler on `127.0.0.1:9000` using
your local AWS credentials with the REAL Bedrock and Polly. It does not emulate API Gateway (no key check,
validation model or throttling). Set `BEDROCK_MODEL_ID` and `AWS_REGION` first.

## Accuracy notes

* `pytest` runs use stubbed AWS clients. They verify the handler logic and the client/handler contract
  (`tests/integration/test_local_stack.py` is a LOCAL contract test, not an AWS test).
* The SAM template passes `cfn-lint`, but it has not been deployed by this repository's tests.
  Model availability, IAM permissions for your chosen profile, Polly voice support and latency
  are only confirmed by deploying and running the live test.
* The Lambda `Errors` alarm only sees unhandled exceptions (the handler turns failures into HTTP errors),
  so an API Gateway 5XX alarm is included too. No alarm action (SNS) is configured; add one if you want
  notifications.
* CORS: the native local agent does not need it. If a browser page calls the API directly, the preflight
  `OPTIONS` request also needs to be allowed without an API key; verify this after deploy.
* Worst case latency is bounded by client timeouts (Bedrock 12 s, Polly 3 s per try) inside the 25 s limit.
