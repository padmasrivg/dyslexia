# Models

`local_agent/vision/text_detection.py` uses `cv2.dnn.TextDetectionModel_DB` when the file named by `DBNET_MODEL`
(default `models/dbnet.onnx`) exists. Place an OpenCV-compatible DBNet ONNX export there, for example the
`DB_TD500_resnet18.onnx` or `DB_IC15_resnet18.onnx` files referenced in the OpenCV text detection and
recognition tutorial (download them from the links in that tutorial and rename or point `DBNET_MODEL` at them).
No model file is bundled and none was downloaded while building this project.

Without a model the agent uses a classical OpenCV morphology detector. The UI and `/api/state` report
which one is active (`input.detector`), so results are never attributed to DBNet when it is not loaded.
